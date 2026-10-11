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

The planned pilot is only successful `open_app` and `open_url` results. Both are
registered legacy tools with compact outputs; their real implementations were
inspected. `open_app` normalizes aliases and may retry the original app spelling;
`open_url` accepts HTTP(S). Both currently invoke the legacy macOS `open` command.
Success means the existing command returned success, not that an application's
window, web content or network load was independently inspected.

Notes, reminders and calendar listings can contain sensitive, lengthy content
and stay outside this pilot, as do all other actions. No providers, routing,
approval policy, database schema, API/settings DTOs, UI, voice or CI workflows
will change. The reply reaches the existing UI through the existing message event.

The next checkpoint will add a bounded text-only completion after persisted
success, local-endpoint gating, bounded input/output, safe optional same-run
intent context, persona, explicit execution status and deterministic fallback.
There will be no tool descriptions, additional execution or automatic retries.

## Existing out-of-scope observations

The two UI findings in the supplied PR #41 review remain in merged Main. They
are not fixed here. GitHub reports Main as unprotected; green CI alone is not
external review. The legacy approval read/resolve sequence is not a new atomic
concurrency claim; this step preserves it and adds no retry of an action.

## Stop gate

One branch, one PR: `feat/yjcore-01-llm-tool-result-communication`.
After final checks and handoff: external ChatGPT review required, no self-merge,
no auto-merge, no YJCORE-02/03 implementation.
