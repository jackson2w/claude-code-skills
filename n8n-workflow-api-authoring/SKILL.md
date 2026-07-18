---
name: n8n-workflow-api-authoring
description: This skill should be used when authoring an n8n workflow as JSON to import via n8n's REST API (rather than hand-clicking in the editor), when an n8n HTTP Request node's attached credential seems to be silently ignored, when an n8n Code node throws "Module 'X' is disallowed", when a `{{ }}` expression field throws a bare "invalid syntax", when downstream Code node fields go missing/undefined after an HTTP Request node, or when importing/updating an n8n workflow via `POST`/`PUT /api/v1/workflows` hits errors like "active is read-only", "PATCH method not allowed", or a referenced error-workflow name not resolving. Trigger phrases include "n8n workflow JSON", "n8n REST API import", "n8n credential not working", "n8n expression invalid syntax", "n8n Module crypto is disallowed", "n8n HTTP Request neverError", "n8n workflow active read-only", "POST /api/v1/workflows".
---

# n8n workflow authoring via REST API

Building an n8n workflow as a JSON file (agent-authored, or scripted) and importing it via
`POST /api/v1/workflows`, instead of hand-clicking every node in the editor. This is a reasonable
middle ground for config-as-code: workflow *logic* (nodes/connections) is versioned and
diffable; *credentials* are still created by hand in the editor so secret values never transit a
file or an agent's context (see the credentials section below). All of the gotchas here were
found the hard way building a real multi-node pipeline (Webhook → external API → GitHub Contents
API with retry logic) and getting it working end-to-end, not from documentation.

## The workflow JSON shape

```json
{
  "name": "my-workflow",
  "nodes": [ {"parameters": {...}, "name": "...", "type": "n8n-nodes-base.X", "typeVersion": N, "position": [x,y], "id": "...", "credentials": {...}} ],
  "connections": { "Node A": { "main": [[ {"node": "Node B", "type": "main", "index": 0} ]] } },
  "settings": { "executionOrder": "v1" }
}
```

Do **not** include `active` or `id` at the top level when creating — see "Import/update API
quirks" below.

## Expression fields (`={{ ... }}`) are not full JavaScript — build complex bodies in a Code node instead

An HTTP Request node's JSON Body (or any `={{ }}` field) looks like it accepts arbitrary JS, but
n8n's expression evaluator does **not** reliably support multi-statement code — an IIFE like:

```
={{ (() => { const x = ...; return JSON.stringify(x); })() }}
```

throws a bare `invalid syntax` with no useful line/column detail. The failure is also silent
about *why* — it just refuses to evaluate. This also breaks in a second, sneakier way: nesting a
second `={{ ... }}`-looking string *inside* an outer expression (e.g. building a `messages`
array where one field's value is itself a quoted `"={{ ... }}"` string) gets misparsed, because
the expression scanner isn't brace-depth-aware across nested `}}` occurrences — it can terminate
the outer expression early at the first inner `}}`, silently truncating the rest of the object.

**Fix:** never build a nontrivial JSON body inline in an expression field. Add a **Code** node
immediately before the HTTP Request node that constructs the full body (real JS, `JSON.stringify`
included) and returns it as a single field, e.g. `{ ...previousFields, request_json:
JSON.stringify(body) }`. The HTTP node's Body field then becomes a trivial single-property
reference: `={{ $json.request_json }}` — this form is reliable.

## Attaching a `credentials` block is not enough — `authentication` must also be set

A node can have a valid `credentials` object (matching a real credential ID) and still silently
send an **unauthenticated** request, with no error, no warning in the API response — the target
API just sees a request with no auth header and returns its own 401, which looks like a bad
credential when the real bug is a missing parameter. The `credentials` field only makes a
credential *available* to the node; a separate `parameters.authentication` field decides whether
it's actually *used*:

- **Generic Header Auth credential**: `parameters.authentication = "genericCredentialType"`,
  `parameters.genericAuthType = "httpHeaderAuth"`.
- **A predefined/built-in credential type** (e.g. GitHub, Slack): `parameters.authentication =
  "predefinedCredentialType"`, `parameters.nodeCredentialType = "githubApi"` (or whatever the
  type name is).

Set both the `credentials` object *and* these `parameters` fields on every HTTP Request node that
needs auth — a credential attached without the matching `authentication` parameter is a silent
no-op.

## HTTP Request nodes throw on non-2xx by default, and `continueOnFail` discards the whole item

If a workflow needs to inspect a status code (a 404 meaning "doesn't exist yet" is normal, a 409
meaning "retry with a fresh value" is normal), the naive approach — read `$json.statusCode` in a
downstream node with `continueOnFail: true` on the HTTP node — silently breaks:

1. By default, any non-2xx response makes the HTTP Request node **throw**, not just return a
   status code to inspect.
2. With `continueOnFail: true`, the item that comes out of a thrown failure is a bare `{ error:
   "<message>" }` — it does **not** merge with whatever fields were on the input item. Every
   field the workflow had built up so far (a computed path, a title, a piece of content) is
   gone, and a downstream node referencing `$json.title` gets `undefined` with no obvious link
   back to "the HTTP node ate my data."

**Fix:** set `parameters.options.response.response.neverError = true` and
`parameters.options.response.response.fullResponse = true`. This makes the node return `{
statusCode, headers, body }` for **any** status code without throwing, so status-code branching
becomes ordinary data inspection (`$json.statusCode === 404`) instead of exception handling with
data loss. (Note the doubled `response.response` nesting — that's how this node's parameter
schema is actually structured, not a typo.)

## An HTTP Request node's output *replaces* the item — it does not carry the input forward

Separately from the above: even a **successful** HTTP Request node's output is just its own
response. It does not automatically merge in whatever fields were on the item flowing into it.
A Code node three hops downstream that assumes `$input.first().json.title` still has the value
set five nodes ago (after two HTTP Request hops in between) will get the *last* HTTP response's
fields instead, silently.

**Fix:** don't rely on implicit pass-through across an HTTP node. Reference the node that
actually produced the data you need, explicitly, from any later Code node:
`$('Build Original Data').first().json.title` — this works regardless of how many HTTP hops
happened in between, as long as that named node executed earlier in the same run.

## The Code node sandbox blocks some `require()` calls

`require('crypto')` throws `Module 'crypto' is disallowed` inside a Code node — the sandbox
restricts which built-in modules are reachable, and `crypto` isn't in the default allow-list.
This is easy to miss until a specific code path (e.g. a hashing/dedup step) actually runs. If you
need a hash and don't need cryptographic properties (just determinism), write a small plain-JS
hash function (e.g. a djb2/FNV-style rolling hash over `charCodeAt`) instead of reaching for
`crypto.createHash`. Plain globals like `Buffer` are fine — it's specifically module `require()`
that's restricted, not every Node.js global.

## Claude/Anthropic responses can include a `thinking` block before the `text` block

If an HTTP Request node calls the Anthropic Messages API and a downstream Code node parses the
response, don't assume `response.content[0]` is the text block — extended thinking (even if not
deliberately requested) can put a `{"type": "thinking", ...}` block first, pushing the real
`{"type": "text", "text": "..."}` block to index 1 or later. Find it by type instead of position:

```js
const textBlock = (resp.content || []).find(b => b.type === 'text');
const text = textBlock?.text;
```

## Import/update REST API quirks

- **`POST /api/v1/workflows` rejects `active` in the body**: `request/body/active is read-only`.
  Strip `active` (and `id`, if present from a prior export) before posting. Activate separately
  via `POST /api/v1/workflows/{id}/activate` (there's also a `/deactivate`) after import.
- **Updating an existing workflow is `PUT`, not `PATCH`**: `PATCH /api/v1/workflows/{id}` returns
  `PATCH method not allowed`. Use `PUT /api/v1/workflows/{id}` with the full `{name, nodes,
  connections, settings}` body — partial updates aren't supported, so `GET` the current
  definition first, mutate what you need in memory, and `PUT` the whole thing back.
- **An error-workflow reference needs the real numeric/string ID, not a name.** If workflow A's
  `settings.errorWorkflow` should point at workflow B, import B first, capture its returned `id`
  from the creation response, and set A's `settings.errorWorkflow` to that ID before importing A.
  A workflow name string in that field does not resolve.
- **`GET /api/v1/credentials` returns id/name/type/sharing metadata only — never secret values.**
  This is safe to call and inspect freely; use it to map credential names to their real
  instance-specific IDs so imported workflow JSON (which can only meaningfully carry a `name` for
  portability) gets wired to working credentials rather than needing manual reselection in the
  editor after every import.
- Credentials **can** be created via `POST /api/v1/credentials` with `{name, type, data: {...}}`
  where the shape of `data` matches the credential type's fields (e.g. Header Auth wants `{name,
  value}`; GitHub API wants `{server, user, accessToken}`). This is fine for credentials that
  aren't themselves a sensitive third-party secret being freshly typed by a human (e.g. an
  n8n-internal API key used only for that instance's own execution lookups) — see the security
  note below for where to draw the line.

## Where secrets should and shouldn't flow

Workflow JSON only ever *references* a credential by id/name — it never embeds a secret value.
Keep it that way deliberately: create any credential holding a genuine third-party secret
(an API key for an external service, a webhook shared secret, a bot token) **by hand in the n8n
editor UI**, not via a script that has the raw value passed through it, so the secret's only
resting place is n8n's own encrypted credential store. Reserve `POST /api/v1/credentials`
scripting for credentials that are themselves low-sensitivity/internal (e.g. an n8n API key
whose only purpose is calling that same n8n instance's own REST API).

When a secret genuinely does need to move between two hosts to get into place (e.g. reading an
existing token from one host's env file to configure something on another), never print it to
a terminal/tool-output transcript and never write it to a file at rest as an intermediate step —
pipe it directly host-to-host (`ssh A "read-the-value" | ssh B "consume-it"`), and have the
consuming side `read` it from stdin into a shell variable used immediately, not from a
positional argument or a file. This keeps the value out of both the visible output and any
on-disk trace, and out of shell history/process-argument visibility on either host.

## Debugging a failed execution via the API

`GET /api/v1/executions/{id}?includeData=true` returns the full run, including
`data.resultData.error` (message/description of what failed and `lastNodeExecuted`) and
`data.resultData.runData` (a per-node log of what each node actually received/returned — the
fastest way to see exactly which field was `undefined` or which status code came back, rather
than guessing from the workflow JSON alone).
