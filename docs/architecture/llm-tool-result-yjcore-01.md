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
outside `1/true/yes/on`) restores the existing deterministic completion after a
backend restart. Explicit `1` is now also restricted to this two-tool pilot;
it no longer requests summaries for arbitrary successful tools.

Only a persisted successful `ToolResult` enters the presentation boundary. The
prompt carries the actual name, bounded validated input, actual output, explicit
`execution_status: success` and the existing persona. Tool data and optional user
intent are JSON-encoded as evidence, with instructions never to follow embedded
commands or claim any additional execution or independently inspected app/site.

Optional intent is kept in memory for at most 128 pending approvals, at most 500
characters each. It is keyed by approval ID and checked against both session and
run IDs when consumed, including delayed approvals. Denial/approval consumes it;
eviction, restart or mismatched IDs mean no intent is supplied. No history/memory
lookup is used to guess the request. Existing persistence and approval semantics
are unchanged; this cache is not an authorization mechanism.

The narrow input boundary requires exactly `app_name` (1–80 characters) or `url`
(1–2048 characters), nonempty output at most 4096 characters and no control
characters. URL narration excludes non-HTTP(S), invalid hosts/ports, credentials,
query strings and fragments. Extra fields and oversized content use the technical
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
malformed envelopes, token-limit termination, blank/non-string content, text over
1200 characters, control characters and structured/code-shaped replies are rejected.
The existing honorific normalization still applies to accepted model text; no
intro or Python-authored action summary is prepended.

The [Ollama chat API](https://docs.ollama.com/api/chat) supplies `message`, `done`,
`done_reason`, optional tool calls and keep-alive. The stricter completion option
is used only for narration; existing chat/planner completion behavior is preserved.

### Exact fallback and outcome integrity

- Disabled, excluded tool/input/output, remote endpoint or known cloud model:
  `Aktion abgeschlossen (<tool>). Ergebnis: <actual output>`.
- Attempted narration fails, times out or returns invalid content:
  `Tool \`<tool>\` ausgefuehrt. Ergebnis: <actual output>`.
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

The wording is model-generated. Shape validation and prompting cannot prove the
truth of arbitrary natural-language claims; the durable execution result remains
authoritative. No claim of hallucination-proof prose is made. Loopback transport
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

The two UI findings in the supplied PR #41 review remain in merged Main. They
are not fixed here. GitHub reports Main as unprotected; green CI alone is not
external review. The legacy approval read/resolve sequence is not a new atomic
concurrency claim; this step preserves it and adds no retry of an action.

## Stop gate

One branch, one PR: `feat/yjcore-01-llm-tool-result-communication`.
After final checks and handoff: external ChatGPT review required, no self-merge,
no auto-merge, no YJCORE-02/03 implementation.
