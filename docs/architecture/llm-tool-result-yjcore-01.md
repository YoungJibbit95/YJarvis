# YJCORE-01 — LLM-owned tool result communication

## Authorization and baseline

The user explicitly authorized this isolated Core step on 2026-10-11, including
the characterization commit and draft PR checkpoint. This supersedes the older
YJW-01D-only scope and no-draft restriction for this step only.

Start Main: `666a9da0482b9b9cd84c1159f4300a46e951bc6b`.
It differs from the supplied `16da0c0` snapshot only by the squash merge of UI
PR #41. Main Baseline CI run `38127668435` has seven successful jobs; Wiki run
`38127668441` passed validation and publication. No other PR was open at start.
Compared with the original architecture baseline `dea0e9e`, Main already includes
domain/persistence contracts, the legacy orchestration extraction, cross-platform
startup, isolated semantic runtimes/providers, setup/packaging, YJCOM-01/02/03,
voice reliability and YJUX-01/02. Those are existing behavior, not work in this PR.

CORE-C2 continuation: the user requested corrections to external review findings
HIGH-01 and MEDIUM-02 at PR #42 head `ad0e1f0d3c1fffadeec09ff2802e438411bbbab4`.
Main and PR base remain `666a9da0482b9b9cd84c1159f4300a46e951bc6b` at the start
gate. UI PR #43 (`codex/yjux02-review-fixes`, head `85437a0`) was subsequently
merged by the user into Main `bad64ef4b9ce67a11b72f11d930e6bf5603ec761`.
Its ten changed UI/test/documentation files have no overlap with this Core patch.
Main [Baseline CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/38141910543)
passed all seven jobs; [Wiki CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/38141910556)
passed validation and publication before integration. The same Core branch takes
this confirmed Main through a normal merge commit, preserving published history
without force-push. Final checks must cover the resulting integrated PR head.

## Checkpoint CORE-A: observed contract

1. `TurnEngine.start_run` persists the user's message and invokes existing routing.
2. A registered tool intent creates a pending approval with the existing session,
   run, tool name and input; it publishes `approval_required` without execution.
3. `handle_approval_decision` rejects missing/resolved approvals. Denial persists
   `denied` and finishes with no tool run. Approval persists `approved` first.
4. It publishes `executing` and calls `ToolRegistry.execute` exactly once. The
   registry dispatches to the existing tool, which validates its own arguments.
5. The returned `ToolResult` is persisted in `tool_runs`, then learning telemetry
   is recorded. The result owns success/failure; model text has no authority.
6. Only success invokes `LegacyResponses.compose_tool_response`. Originally the
   default `JARVIS_TOOL_SUMMARY_VIA_LLM=0` used `Aktion abgeschlossen (...).
   Ergebnis: ...`. Explicit `1` requested a completion for any successful tool,
   with a 20-second HTTP read timeout and a technical fallback.
7. `finish` persists one assistant message, then publishes the same text and the
   terminal state using the original session/run IDs. Existing compaction follows.

The first commit adds tests using the existing real SQLite lifecycle fixture for
this ordering, approval denial, failed tools, result-persistence failure, single
message delivery, repeated decisions and explicit rollback. No production code
is changed at this checkpoint.

## Implementation boundary

The pilot is only successful `open_app` and `open_url` results. Both are
registered legacy tools with compact outputs; their real implementations were
inspected. `open_app` normalizes aliases and may retry the original app spelling;
`open_url` accepts HTTP(S). Both currently invoke the legacy macOS `open` command.
Success means the existing command returned success, not that an application's
window, web content or network load was independently inspected.

Notes, reminders and calendar listings can contain sensitive, lengthy content
and stay outside this pilot, as do all other actions. No providers, routing,
approval policy, database schema, API/settings DTOs, UI, voice or CI workflows
change. The reply reaches the existing UI through the existing message event.

## Checkpoint CORE-B: narration contract

`JARVIS_TOOL_SUMMARY_VIA_LLM` now defaults to `1`. Explicit `0` (or another value
outside `1/true/yes/on`) selects deterministic completion after a
backend restart. Explicit `1` is now also restricted to this two-tool pilot;
it no longer requests summaries for arbitrary successful tools.

Only a persisted successful `ToolResult` enters the presentation boundary.
`narration_evidence` recognizes the actual legacy output contract, requiring exact
`App geoeffnet: <target>` or `URL geoeffnet: <target>` equality. App targets must
match either `normalize_app_name(raw_input.strip())` or `raw_input.strip()`;
the actual result chooses which path completed. This preserves the existing
tool's original-spelling retry without adding a tool execution. A differing
target, malformed result, or unsafe target representation gets no model request.

The prompt carries actual tool name, bounded input/output, explicit
`execution_status: success`, **`evidence_grade: os_command_completed`**, actual
target/kind and the existing persona. Input, target, output and optional intent
are JSON data in the user-role evidence message, never interpolated into the
system instruction. They are not execution authority.

Optional intent is kept in memory for at most 128 pending approvals, at most 500
characters each. It is keyed by approval ID and checked against both session and
run IDs when consumed, including delayed approvals. Denial/approval consumes it;
eviction, restart or mismatched IDs mean no intent is supplied. No history/memory
lookup is used to guess the request. Existing persistence and approval semantics
are unchanged; this cache is not an authorization mechanism.

The narrow input boundary requires exactly `app_name` (1–80 characters) or `url`
(1–2048 characters), nonempty output at most 4096 characters and no control
characters (including Unicode format/bidi and line separators). App targets
allow alphanumeric characters and ` ._()+-` only. URL narration excludes
non-HTTP(S), invalid hosts/ports, credentials, query strings, fragments, whitespace,
quotes, backslashes and markup delimiters. Percent-encoded URL paths remain opaque
data: they are never decoded, interpreted as instructions or normalized into a
different resource. Extra fields and oversized content use the technical
path rather than truncating evidence or sending unrelated data. The persona is
limited to 8000 characters; an oversized persona also uses the technical path.

The completion goes only to literal `127.0.0.1`, `::1`, or `localhost` (canonicalized
to `127.0.0.1` without DNS). Credentials, endpoint paths/query/fragment, HTTP proxy
environment settings, redirects and known `:cloud`/`-cloud` model names are excluded.
This is separate from ordinary chat's existing endpoint configuration. No new
provider, discovery request or classification call is added.

Exactly one nonstreaming completion is attempted per eligible completed result:
8-second total async timeout, 8-second HTTP read timeout, temperature 0.1,
`num_predict=256`, existing `JARVIS_OLLAMA_KEEP_ALIVE`, and no tool descriptions.
The total deadline includes connect/write/read/pool waits. There is no automatic
retry. A completed assistant text response is required. Tool/function calls,
malformed or duplicate-key JSON envelopes, token-limit termination, blank/non-string
content, text over 1200 characters and control characters are rejected. The strict
transport preserves content verbatim, including boundary whitespace, for final
validation. Ordinary completion callers retain their earlier parsing contract.

### CORE-C2: fail-closed claims boundary

HIGH-01 was reproduced with four real SQLite/TurnEngine tests: additional email
and file actions, the wrong app, `SYSTEM:` instructions and app readiness all
reached the assistant sink on the reviewed head. Format checks were insufficient.
MEDIUM-02 had the same root at the evidence boundary: the subprocess exit code
supports a completed opening command, not verified visible/loaded/ready state.

The correction accepts only this small **closed compositional language**:

```text
Sentence = "Der " Command " für " Target " wurde erfolgreich " Completion Address "."
         | "Für " Target " wurde der " Command " erfolgreich " Completion Address "."
Command = "Öffnungsbefehl" | "Befehl zum Öffnen"
Completion = "ausgeführt" | "abgeschlossen"
Address = "" | ", Sir"
Target = "die " actual_target_kind " " exact_double_quoted_actual_target
```

The entire model response must match, with the exact case-sensitive target derived
from the actual result. No arbitrary clause, resource, tense or extra sentence is
accepted. This is a recognition grammar, not a growing blacklist of German action
verbs or a second model/classifier. The LLM generates the whole sentence; Python
does not select, assemble, repair or paraphrase a successful narration. For example,
both model replies below pass unchanged, including through the real HTTP parser,
assistant-message persistence and publication:

- `Der Öffnungsbefehl für die App "Safari" wurde erfolgreich ausgeführt.`
- `Für die App "Safari" wurde der Befehl zum Öffnen erfolgreich abgeschlossen, Sir.`

No honorific or whitespace normalization runs after validation: it could change
a legitimate target such as `mein Herr`. Prompt injection may influence model
output, but cannot expand this accepted language or initiate an action. Wrong
targets, extra email/file actions, ready/visible/loaded/read claims, role spoofing,
code and even otherwise true prose outside the grammar use the technical fallback.

The [Ollama chat API](https://docs.ollama.com/api/chat) supplies `message`, `done`,
`done_reason`, optional tool calls and keep-alive. The stricter completion option
is used only for narration; existing chat/planner completion behavior is preserved.

### Exact fallback and outcome integrity

- Eligible pilot evidence, but flag disabled, excluded endpoint/model/persona,
  timeout, failed request or rejected model response:
  `OS-Öffnungsbefehl erfolgreich abgeschlossen (<tool>). Ziel: "<actual target>".
  Fenster- oder Seitenzustand wurde nicht geprüft.`
- Successful pilot result with unrecognized/unsafe evidence (including when the
  flag is disabled): `ToolResult meldet Erfolg (<tool>). Eine geprüfte Rückmeldung
  zum Öffnungsbefehl ist nicht verfügbar.` This reports only the persisted status;
  it never reflects injected output, guesses a target or converts it to failure.
- Other successful tools keep their existing technical response:
  `Aktion abgeschlossen (<tool>). Ergebnis: <actual output>`.
- Failed execution stays on the existing error path without a narration request:
  `Tool fehlgeschlagen (<tool>): <actual error>` with terminal `error`.
- Denial stays on the existing no-execution path. No tool result is invented.

The model never receives execution authority. Its response cannot update the
stored tool run, learning outcome, approval, run ID or session ID, invoke another
tool, or cause an action retry. `finish` still produces exactly one stored and
published assistant message followed by the existing terminal state.

## Verification and limitations

Tests use the existing real temporary SQLite fixture, the real registry/tool
implementations with only the OS subprocess boundary replaced, and the actual
HTTP completion parser with a controlled transport. They cover persistence before
narration, default-on/explicit-off, two different model-authored answers, both
pilot tools, denial/failure, unchanged IDs/events, single message, duplicate
decisions, session/run isolation, restart/eviction, timeouts, nonlocal endpoints,
sensitive/oversized data, invalid model output and forbidden model tool calls.

The wording is model-generated but deliberately restricted to the grammar above.
Arbitrary natural-language truth is **not** proven; legitimate wording outside
this small German language also falls back. The pilot is not a general semantic
validator. Persona expression is limited to the permitted wording and optional
`Sir`; actual local-model acceptance rate/quality has not been measured. The
tool implementation and persisted result remain trusted evidence: this boundary
cannot prove that a faulty tool or OS reported the truth. Quoted targets remain
opaque resource names, including instruction-like text in URL paths; no claim
about their contents is made. Loopback transport
and known cloud-name exclusion cannot attest that a user-installed local server
or a renamed model itself forwards no data; a real local Ollama/model is assumed.
This PR does not port the legacy macOS tools to Windows or certify app/window
state. Native tool/model/hardware end-to-end checks: **NOT RUN**. Real model and
hardware latency: **NOT MEASURED**.

CORE-A: focused characterization/lifecycle tests **58 passed** before runtime
changes. Final local and GitHub results are recorded in the PR handoff.

Rollback: set `JARVIS_TOOL_SUMMARY_VIA_LLM=0` in the backend process environment
and restart, or revert the PR. No settings, user data or database migration is
required. Ordinary conversation, routing, voice and approvals keep their existing
paths. YJCORE-02 capability discovery and YJCORE-03 model-driven selection are
separate future authorizations, not work in this PR.

## Existing out-of-scope observations

The UI follow-up PR #43 is now merged into the confirmed Main used for final
Core integration. No UI file is changed by the Core diff. GitHub reports Main
as unprotected; green CI alone is not external review.

**Separate approval-concurrency security finding (not fixed in this scope):**
The subsequent [YJSEC-01 security step](atomic-approval-claim-yjsec-01.md)
addresses this finding in its own PR; the following describes the YJCORE-01 baseline.
`handle_approval_decision` reads pending status, then separately calls
`resolve_approval` before execution. Two concurrent decisions can both observe
pending before either resolves; the current update is not an atomic conditional
claim checked by the caller. Sequential duplicate decisions are rejected, but
the tests do not claim exactly-once behavior under concurrent approval requests
or multiple workers. A separate authorized step should atomically claim the
pending approval and execute only for the winner, with real concurrency tests.
This correction adds no retry/second execution and leaves the DB and lifecycle
unchanged. Narration validation does not resolve this separate execution risk.

## Stop gate

One branch, one PR: `feat/yjcore-01-llm-tool-result-communication`.
After final checks and handoff: external ChatGPT review required, no self-merge,
no auto-merge, no YJCORE-02/03 implementation.
