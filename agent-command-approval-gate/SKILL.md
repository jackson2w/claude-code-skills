---
name: agent-command-approval-gate
description: This skill should be used when building or reviewing an approval gate that decides whether a self-hosted agent's shell command needs human approval — OpenClaw/Olu, Hermes/Chuka, or any agent whose exec tool needs a human in the loop for privileged or outbound actions. Covers the three command-matching designs and why only one is safe (substring over-gates, anchored regex under-gates, command-position tokenizer is correct by construction), the full wrapper-bypass catalogue, the heredoc/backtick false positive the tokenizer introduces and its provable fix, block-vs-gate as originating-vs-continuing, the refactor regression a unit harness structurally cannot catch, OpenClaw's 512-char approval cap, the three-case live-fire protocol, and drift detection for a gate living where no playbook deploys it. Built across `dfw` (OpenClaw `admin-changes-gate`) and `hermes` (Hermes `outbound-email-approval`) 2026-09-01 to 2026-09-05. Trigger phrases include "approval gate", "pre_tool_call hook", "before_tool_call", "gate agent commands", "requireApproval", "which commands need approval", "agent sent email without asking", "gate regex bypass", "sudo bypasses the gate", "command position matching", "tokenize shell command", "gate prompts on read-only commands", "false positive approval prompt", "hey compose blocked", "agent-send-email.sh gated", "approval description too large", "live-fire gate test", "gate manifest drift", "DANGEROUS_PATTERNS", "tools.exec.security full".
---

# Agent command approval gates

How to decide that a command an agent is about to run needs a human. Built and re-built across two
hosts over five days; every failure mode below is one that actually shipped.

The config-and-hook side of gating lives in `openclaw-deployment` (Gotcha 2, `tools.exec.security`
vs `ask`) and `hermes-agent-deployment` (`DANGEROUS_PATTERNS`, `approvals.mode`). **This skill is
about the part those don't cover: matching.** Getting the hook to fire is easy. Deciding *which*
commands it fires on is where every real bug was.

## Why matching is the hard part

An approval gate has exactly two ways to fail:

- **Under-gate** — a privileged command runs with no prompt. Silent. Presents as "no prompt fired",
  indistinguishable from the gate not being installed. This is the failure that matters.
- **Over-gate** — a harmless command prompts. Noisy, fail-safe, and *not* free: an approval the
  human clicks through without reading is worth less than no approval at all. Both implementations
  here carry that reasoning in their own headers.

So the target is not "match aggressively." It is **match exactly the invocations, and nothing that
merely mentions them.** That turns out to be a parsing problem, not a pattern problem.

## The three designs, in the order they get invented

Every implementation walks this path. Skip to design 3.

### 1. Substring — over-gates

```ts
re: /\bhey\s+compose\b/
```

`grep hey compose`, `cat` of a script containing the string, `ls -l /path/to/agent-send-email.sh`
— all prompt. Chuka found this first on hermes: a read-only inspection of the sender's own path
tripped a prompt. Safe, but it trains reflexive approval.

### 2. Anchored regex — UNDER-gates, do not ship this

The natural fix is to anchor to "start of a command":

```ts
re: /(?:^|[;&|]\s*|(?:^|\s)[A-Z_][A-Z0-9_]*=\S*\s+)hey\s+compose\b/
```

This looks right and is materially worse than what it replaced, because it moves the failure from
over-gating to under-gating. Verified bypasses against exactly this pattern:

| Shape | Why it slips |
|---|---|
| `sudo hey compose …` | `sudo` is not start-of-string, a separator, or an env assignment |
| `env` / `nohup` / `time` / `doas` / `command` / `exec` prefix | same |
| `$(hey compose …)` | `$(` is not in the separator class |
| `` `hey compose …` `` | backtick is not either |
| `( hey compose … )` | subshell open is not either |
| any invocation on line 2+ of a multi-line command | `^` without the `m` flag is start-of-*string* |

Each is patchable by adding an alternation. That is the tell that the design is wrong: **the next
wrapper someone invents is a new hole.** A regex cannot see command position because command
position is a property of shell grammar, not of text.

### 3. Command-position tokenizer — correct by construction

Split into segments at every point a new command can begin, strip the things that wrap a command
without changing which command it is, then match on `argv[0]`/`argv[1]`.

Reference implementation (hermes, Python — `outbound-email-approval/__init__.py`):

```python
_SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|&\n]|\$\(|`|\(")
_TRANSPARENT_PREFIXES = frozenset(
    {"sudo", "env", "command", "exec", "nohup", "time", "builtin", "doas"}
)
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

def _command_positions(command: str):
    """Yield the argv of each command position in a shell string."""
    for segment in _SEGMENT_SPLIT.split(command):
        tokens = segment.strip().split()
        index = 0
        while index < len(tokens) and (
            _ENV_ASSIGNMENT.match(tokens[index])
            or tokens[index] in _TRANSPARENT_PREFIXES
        ):
            index += 1
        if index < len(tokens):
            yield tokens[index:]
```

The TypeScript port (dfw) adds one thing worth copying — **basename comparison with a trailing-paren
strip**, because the splitter leaves `$(hey compose …)`'s closing paren attached to the last token:

```ts
function cmdWord(token: string | undefined): string {
  if (!token) return "";
  return (token.split("/").pop() ?? token).replace(/\)+$/, "");
}
```

`FOO=1 sudo /usr/local/bin/hey compose …` now presents as `["hey", "compose"]`; `grep hey compose`
presents as `["grep", …]`. Every bypass in the table above is covered without enumerating any of
them.

**Keep substring matching for shapes where the string appearing anywhere means the mutation is in
play** — an admin-server endpoint like `127.0.0.1:8790/changes`, for instance. Those never
false-positive on reads, so the tokenizer buys nothing. Mixed matching is correct here, not lazy.

## The tokenizer's own false positive — know it before you ship

`SEGMENT_SPLIT` contains `\n` and a backtick. Both are correct for shell. Both mean **heredoc
bodies and markdown inline code spans get parsed as command positions.** Observed live on dfw
2026-09-05 when the agent wrote its own test results into a memory file:

```
GATED    cat >> notes.md <<'EOF' … prose containing `agent-send-email.sh --help` … EOF
GATED    echo `agent-send-email.sh --help`
BLOCKED  echo `hey compose --to a@b`
GATED    heredoc with agent-send-email.sh at the start of a line
silent   echo 'agent-send-email.sh --help is the command'    (no backtick)
silent   echo the script agent-send-email.sh exists           (mid-sentence)
```

The third line is the sharp end: **an agent cannot document its own gate**, because prose
mentioning the blocked command inside backticks is itself blocked. Agents write markdown
constantly — memory files, notes, handoff entries — so this fires in normal operation, not in
contrived cases.

**The fix that is provable rather than heuristic: strip single-quoted heredoc bodies before
tokenizing.** `<<'EOF'` is literal by definition — no expansion of `$( )`, backticks, or variables
— so its body can never execute anything, and removing it from consideration cannot create a
bypass. Unquoted `<<EOF` *does* expand and must stay tokenized.

Bare backticks outside a heredoc are the unfixable half: distinguishing markdown from command
substitution needs quoting state that a split-based tokenizer does not have. **Accept the
over-gating.** Removing backtick from the separator class to quiet it re-opens a genuine bypass,
and that trade is backwards.

## Block vs gate: originating vs continuing

Not a risk ranking. The line that held up in practice:

- **Block** the shape that is wrong no matter who approves it. On both hosts, `hey compose` sends
  as the human's own identity, so a prompt asks him to bless a message already addressed wrongly —
  and when it is the message he asked for, approving is the natural reflex. Blocking with a
  `blockReason` naming the correct path is better: the agent self-corrects in the same turn.
- **Gate** anything that continues an existing thread or sends as the agent's own identity.
- **Leave open** reads, search, triage, calendar, contacts, and drafts. `--draft` is the review
  lane — an unsent draft never leaves the account — so it stays open even for an otherwise blocked
  verb.
- Carve-outs need checking against the CLI's real help output, not assumption. `compose --thread-id`
  is semantically a reply, so it is *gated*, not blocked.

## The regression a unit harness structurally cannot catch

The first tokenizer port changed `classify()` from returning a string to returning an object, and
left one interpolation behind:

```ts
const verdict = classify(command);          // now an object
…
description: `Gated: ${gatedLabel}\n` +     // the old string variable — undefined
```

Result: **every gated path threw `ReferenceError`** while the blocked and pass-through paths
worked normally. A 42-case harness reported all green, because it tested `classify()` — and the
defect was in the caller consuming its return value.

**A unit test over an extracted pure function cannot see a defect in its caller.** Test through the
real entry point: import the plugin, stub only the SDK module to capture the registered handler,
and fire synthetic events at it.

```js
const r = await handler({ toolName: "exec", toolKind: "shell", params: { command } });
const outcome = r?.block ? "blocked" : r?.requireApproval ? "gated" : "pass";
```

Note also that `node --experimental-strip-types --check` validates **syntax only** and passes an
undefined identifier cleanly. `tsc --noEmit` names it immediately. A green `--check` is not a green
build.

## OpenClaw's 512-char approval cap

OpenClaw **rejects an approval request whose `description` exceeds 512 characters**, and approval
failures are fail-closed — so an over-long description *blocks a legitimate action* and presents as
"the gate is broken," not "the message was too long." Slice the embedded command:

```ts
description: `Gated: ${verdict.label}\nCommand: ${command.slice(0, 240)}\nApprove to run once, or deny.`
```

Hermes has no known equivalent cap; apply the bound anyway. Also set `timeoutBehavior: "deny"` with
a few-minute `timeoutMs`, so an unnoticed prompt fails closed instead of executing hours later.

## Live-fire protocol — three cases, and the third is not optional

A gate verified only by harnesses is a gate that has never been observed. Harnesses cannot
distinguish a loaded gate from an unloaded one; on dfw a test was once reported as "gate verified"
when no prompt had ever fired. After any restart that loads new gate code, run exactly this, one
command at a time, with the human watching:

1. **Positive baseline** — a gated command in its plainest form. Expect a prompt.
2. **Positive via wrapper** — the same command behind `env` or `sudo`. Expect a prompt. *This is
   the case that distinguishes the tokenizer from the regex it replaced.*
3. **Negative** — a read-only command that merely mentions the gated one, e.g.
   `grep -c compose /usr/local/bin/agent-send-email.sh`. Expect **no prompt**. A prompt here means
   the old code is still loaded.

Choose commands inert even if approved by mistake (`--help` works well). Stop immediately if 1 or 2
produce no prompt: that is a fail-open gate, which is worse than any bug you were testing for.

**Read the prompts, not the journal, to attribute results.** The gateway journal logs
`plugin.approval.waitDecision` with a duration and an id and **no command text**, so it cannot say
which command any decision belongs to. The Telegram approval messages carry the full command. Two
hours were lost inferring attribution from surrounding log lines and getting it wrong.

## Drift detection when the gate lives where nothing deploys it

An agent-owned plugin under the agent's home is invisible to Ansible and to Claude Code, so a
rebuild drops the only enforcement gate silently. The arrangement that works:

- The **agent** publishes sha256 of its live plugin files hourly to a path on the shared exchange
  channel (a script-payload cron job — no model calls).
- A **root health publisher** compares those hashes against a copy vendored into the host's Ansible
  repo, emitting `gate_manifest_missing`, `gate_manifest_age_min`, and `gate_files_mismatched`.
- The **peer host** alerts on all three, so a dead agent cannot hide its own drift.

**Honest limit, and state it in the code:** this asks the subject to self-report, so it detects
*accident* — a rebuild, an unrecorded edit, a stopped job — and not an agent publishing a
stale-but-matching manifest. Root could hash the plugin directly and close that; on this fleet it
is deliberately not done, because the agent's home is a boundary the human set.

Expect the first firing to catch **you**, not the agent: vendoring is manual, so the human-side copy
goes stale the moment the agent patches and publishes. That is the check working.

## Review checklist

- [ ] Matching is command-position, not substring, for anything that appears in ordinary prose
- [ ] Every wrapper in `_TRANSPARENT_PREFIXES` is covered — verify with a real test, not by reading
- [ ] Single-quoted heredoc bodies stripped before tokenizing
- [ ] Tests fire the **handler**, not the classifier
- [ ] Both directions covered: gated shapes prompt, read-only mentions stay silent
- [ ] Approval description bounded (≤512 for OpenClaw), no `undefined` interpolation
- [ ] `timeoutBehavior: "deny"`
- [ ] Every send/mutation route is gated — a new route added later silently defeats the gate
- [ ] Live-fire run after the restart that loads it, all three cases
- [ ] A vendored copy plus drift detection exists if the plugin lives outside IaC
