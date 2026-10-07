# YJ2-03: TurnEngine orchestration shell

## Scope and baseline

This is a behavior-preserving extraction from `AgentService`, based on inspected
`main` **ffe58b2d9259129641244524689165c08d548c84**. Since the architecture's original
`dea0e9e...` baseline, YJ2-00 (CI), YJ2-01 (inert domain contracts) and YJ2-02
(persistence migration framework) were accepted. The duplicate YJ2-01 merge is
history-only and is left intact.

The user explicitly authorized YJ2-03 with Codex on 2026-10-07 and retained the
one-goal/one-PR/external-review stop gate. The original architecture source is
unchanged. The supplied [platform addendum](02_WINDOWS_CROSS_PLATFORM_ARCHITECTURE_ADDENDUM.md)
has SHA-256 `93dd6aa5763bb52e5ba3263a9ad8a42b633451bd4882d4021cdbec0b54fbb6bd`.
It records targets; this PR does not make the legacy application Windows-ready.

## Responsibility boundary

Before: `AgentService` contained setup, turn orchestration, safety/confirmation
sequencing, reply/routing precedence, prompt construction, streaming, events and
approval execution bookkeeping.

After:

```text
unchanged FastAPI callers
        |
AgentService (constructor/configuration + compatibility entry points)
        |
TurnEngine (turn and single-approval lifecycle)
        |-- LegacyRouting (existing decision sequence)
        |-- LegacyResponses (existing prompts, streaming, persistence/event output)
        |-- existing Database, LearningEngine, ToolRegistry and memory helpers
```

`AgentService` retains its constructor and `start_run`, `start_run_background`,
and `handle_approval_decision` signatures. Environment defaults and clamps are
unchanged; configuration is supplied to the adapter that consumes it. The pending
confirmation dictionary remains shared with the facade. Internal private helper
locations change; no FastAPI, desktop or persistence caller needs modification.

`TurnEngine` persists input, starts the existing state sequence, consumes one
routing result, creates at most one approval, or asks for a streamed response.
It also retains the existing approval lifecycle: validate status, resolve the
decision, execute through the existing registry, persist the result/metrics,
respond and compact. It contains no regex, SQL, platform dispatch, tool-specific
conditionals, prompt building or token buffering.

`LegacyRouting.route(...)` is the narrow replacement seam. Its internal
`LegacyRoute` carries a local reply, one legacy `ToolCallIntent`, or conversational
fallback, together with the effective input after confirmation. It is not a new
public/domain/persistence contract or execution authority. Tests substitute all
three outcomes without changing the lifecycle or APIs.

The adapter deliberately keeps safety checks, pending confirmations, learning
instructions, local replies, learned commands, heuristic routing and optional
planner fallback together in their original order. Splitting/redesigning the
router, fast paths and planner adapter remains YJ2-04. ToolSpec/runtime and policy
replacement remain YJ2-05/06. There are no new domain integrations, plans, policy
verdicts, event versions, migrations, providers, frontend or voice modules.

## Preserved behavior

- Input persistence precedes `received` and `thinking` events.
- Safety blocking precedes confirmation and routing. Accepted confirmation
  restores the original input; unrelated input discards a pending confirmation.
- Reply precedence stays learning instruction, quick reply, status, utility,
  clarification, then learned/heuristic/optional planner selection.
- A tool intent creates one pending approval and never executes directly.
  Approval status is persisted before execution; denial never executes.
- Successful and failed tool results keep their tool-run rows, learning counters,
  learned-trigger attribution, response text and terminal state order.
- Prompt history, memory context, tool statistics, token size/time buffering,
  final normalization, empty-stream fallback and error handling are retained.
- `finish()` merely shares the repeated sequence: persist assistant message,
  publish message, publish terminal state. Compaction remains at the original
  call sites (successful conversational completion and completed tool attempts).
- Background scheduling and sequential rejection of already-decided approvals
  remain unchanged. This extraction adds no concurrency/idempotency guarantee.

## Platform boundary and verification

New orchestration contains no OS-specific process commands, path rules or platform
conditionals. Profile loading is injected; OS effects remain behind the existing
ToolRegistry. Legacy providers and persona wording remain unchanged. This is
platform-neutral coordination, not evidence of Windows/macOS integration parity.

The initial 31 characterization cases passed against the original service before
extraction, then against the extracted implementation. Further tests cover token
timing, prompt context, learned-command precedence and the replaceable route seam.
They use real temporary SQLite databases and actual safety/routing/learning/memory
helpers, with fake model I/O and tool execution; no system apps or models run.

Windows baseline before runtime changes: Python **3.11.1**, Windows 11 Pro x64
**10.0.26100**, 413 tests passed and 3 failed. Existing failures were:

1. `test_import_and_validation_do_not_access_runtime_services`: isolated bytecode
   loading raised `AttributeError: 'bytes' object has no attribute 'co_filename'`.
2. `test_timestamp_order_compares_instants_across_dst_fold`: no installed `tzdata`
   / `Europe/Berlin` zone database in this Windows environment.
3. `test_resolve_path_expands_home`: the test sets `HOME`, while native Windows
   `Path.expanduser()` uses the Windows home environment.

These pre-existing failures are not skipped, suppressed or repaired in this PR.
Exact final local command results and Linux CI links are recorded in the PR.
No interactive Windows, macOS/Apple Silicon, Ollama, microphone, STT/TTS, OS-tool
or packaged desktop success is claimed. Desktop verification is static only.

## Risks, review and rollback

The known 21 npm vulnerabilities (2 critical, 11 high, 7 moderate, 1 low), absent
server-side branch protection, unlocked Python transitive dependencies and
platform runtime coverage gaps remain. No dependency or CI configuration changed.

Review the actual diff for preserved branch precedence, confirmation semantics,
approval-before-execution ordering, error/compaction boundaries and event payloads.
Confirm that YJ2-04 can replace routing without changing FastAPI, DB or the entire
turn lifecycle, and that the engine has not become a renamed monolith.

Rollback: revert this PR's squash commit, or its commits in reverse order if
merged without squashing. No schema/data migration is introduced, so existing
databases need no downgrade. Do not delete runtime data, profiles or models.

After the PR checks and handoff: **STOP**. External ChatGPT review and explicit
user authorization are required before any next step. Neither YJW-00 nor YJ2-04
has been started.
