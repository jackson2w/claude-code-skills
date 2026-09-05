---
name: pause-handoff-email
description: This skill should be used whenever a working session pauses rather than completes — when Will says "good pause point", "let's pause here", "I'll pick this up later", "that's enough for today", "wrapping up", "done for now", or hands work back while something is still mid-flight. It defines the pause-handoff email sent to Will covering unverified claims, owed work, phrases to resume each thread, and steps only he can run. Also applies when he asks to "email me the flags", "send me what's outstanding", "what do I need to do", or "how do I pick this up later".
---

# Pause handoff email

A terminal summary scrolls away and cannot be read from a phone. When a session pauses, anything
still outstanding — an unverified claim, a decision only Will can make, a command only he can run
— otherwise survives only in a transcript he would have to reopen a laptop to find. This skill
sends that state to his inbox instead.

Standing convention from Will, 2026-09-05: *"whenever we pause, email me the flags and gaps and
things that need my attention, along with guidance on how to resume the topic with you and any
steps i need to run myself."*

## When to fire

Fire on **any pause**, not only on an explicit end-of-session signal. A pause is any point where
Will stops driving and work remains: a stated pause, a handoff, a blocked step waiting on him, or
a session ending with items open.

This is a broader trigger than the homelab wrap-up ritual (memory, skills, tooling, git status),
which fires only on an explicit end-of-session signal. Run that ritual **first** when it applies —
the email should describe memory and git state already settled, never promise it. A handoff email
listing work as recorded when it is not yet committed is worse than no email.

Skip only when nothing is outstanding: no unverified claim, no owed work, nothing blocked on Will.
Say so in one line rather than sending an email with five empty sections.

## The five sections, in order

### 1. Flags — claimed but not proven

Anything deployed-but-unverified, verified only on a privileged path, tested at the wrong layer,
or resting on inference rather than observation. For each one, state **the exact check that would
settle it**: a literal command, and what pass and fail each look like.

This section is the reason the email exists. The recurring failure mode is reporting success too
early, and a flag Will can resolve in one command is worth more than a paragraph of hedging.

Include anything deliberately left in an odd state, with the reason. Five threads held open on
purpose read as five stalled threads unless the email says otherwise.

### 2. Gaps — real work that is owed

What remains, including work deliberately not done and why, so a deferred decision does not read
later as an oversight. Name what blocks each item: a decision, a credential, a dependency.

### 3. How to resume each thread

Short trigger phrases Will can send back cold, mapped to what they will pick up. He should not
have to reconstruct context to restart a thread. Add a general fallback — asking what is
outstanding on a topic — for threads gone stale.

### 4. Steps that are his, not mine

Separate explicitly. Anything blocked on a UI action, a credential that must not pass through a
transcript, or a judgment call that is not mine to make. Give exact commands where they exist.

### 5. What shipped and is verified

Brief. Enough that the current state is trustable without re-reading anything.

## Sending it

Use the agent mail path, not a ledger-styled report — this is correspondence, not a status
report:

```bash
scp -q <body>.txt <attachment>.md hermes:/tmp/
ssh hermes "/usr/local/bin/agent-send-email.sh \
  --to willie@williejackson.com \
  --subject 'Pause handoff YYYY-MM-DD — <topic>' \
  --body-file /tmp/<body>.txt \
  --attach /tmp/<attachment>.md; rm -f /tmp/<body>.txt /tmp/<attachment>.md"
```

Write a **plain-text body** that reads on a phone without horizontal scrolling, and attach the
same content as markdown for reading on a laptop. The sender exists on both `hermes` (sends as
`chuka@williejackson.com`) and `dfw` (sends as `olu@williejackson.com`); prefer whichever host the
work concerned. See the `infisical-secrets-manager` and `agent-vault-credential-broker` skills for
the surrounding infrastructure.

**Sign the body `-- Claude Code`.** The From address is fixed by root-owned config and there is no
Claude Code identity, so an unsigned message reads as the agent's own.

Expect an approval prompt on Will's Telegram — the send is gated. If neither host is reachable,
say so and put the full handoff in the terminal instead; never silently skip it.

## Rules that make it worth reading

- **Every flag carries its check.** A flag without a command Will can run is an anxiety, not a
  handoff.
- **State what is unproven as unproven.** Unit tests passing is not the same as a live path
  confirmed; a root-run test is not the same as a confined-agent test. Say which one happened.
- **Deferred decisions are listed, not buried.** If a judgment call was left to Will, it belongs
  in section 4 even if mentioning it feels redundant.
- **Do not pad.** Sections 1 and 4 are the reason he opens it. Section 5 is a paragraph, not a
  changelog.
- **Never include a secret**, and never ask him to paste one back. Credential steps say where the
  value lives and what to write, never the value.

## Related

- Homelab wrap-up ritual and its ordering: `feedback_session_wrapup_protocol` memory.
- Verification standards the flags section depends on:
  `feedback_verify_against_real_execution_path` and `feedback_verify_via_most_authoritative_source`
  memories — a privileged-path or wrong-layer test is exactly what belongs in section 1.
