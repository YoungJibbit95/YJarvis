# YJCOM-03 — LLM-first Communication & Live OS Facts

## Start gate, architecture and boundaries

Base: `main` at `b0ef65f712109e3ee7a93b21d3a2fd9ae40ef3a4` after YJCOM-02 PR #38 merged; full [main 7/7 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37947056328) and [main Wiki validate/publish](https://github.com/YoungJibbit95/YJarvis/actions/runs/37947056330) succeeded, no concurrent open PR. This is a small vertical step, **not** a V2 runtime migration.

**Product decision:** Normal conversation and the wording of current OS facts belong to the LLM. Python/YJarvis owns available capabilities, verified observations, permissions, errors and lifecycle. Never report an unobserved state as fact.

## Direct-reply inventory and changes

Prior production `LocalFastPaths.route()` called `quick_local_reply` (thanks, greetings, acknowledgment, generic capability promises), `quick_system_status_reply` (configuration summary) and `quick_utility_reply` (canned time/date/readiness). Those three answer paths are now **disconnected from production routing**. Their legacy helper definitions remain temporarily for compatibility/test characterization but are inert in the actual TurnEngine path; no new canned-answer variants were introduced.

`quick_clarification_reply` still asks for a missing **technical action parameter**, including the YJCOM-02 reminder follow-up. `LegacySafetyStage` blocks or confirms safety-sensitive input before any normal response/OS tool. Explicit learned commands, registered heuristic actions and the opt-in Semantic-Pilot still go through the prior ToolRegistry and durable Approval. Policy refusals, missing permissions, unknown-tool clarification, model failure and Tool errors remain legitimate deterministic **technical** messages.

`LegacyResponses.compose_tool_response()` still defaults to a faithful tool-result template, with its existing `JARVIS_TOOL_SUMMARY_VIA_LLM=1` opt-in for LLM wording. We did **not** change this action-result lifecycle in YJCOM-03: it merits its own small approval-/result-integrity step.

## One narrow read-only Toolkit registration, two model-visible functions

The new `ReadOnlyToolkit` explicitly registers:
- `system.local_datetime`: local **aware** timestamp, ISO date, ISO weekday, UTC offset, reliable IANA timezone identifier if available, timezone label, and `datetime.now().astimezone()` OS-clock source. A timezone label is not falsely called an IANA name.
- `toolkit.capability_snapshot`: a bounded, structured snapshot derived from live registered `ToolRegistry.list_specs()` and actual implementation/platform checks, plus `CAPABILITY_CATALOG` metadata kept clearly **known-only, not wired or executable**.

There are exactly **two** read-only callable names. Both take a strictly empty argument object, are side-effect-free, and receive a narrowly coded no-approval exception **only** in `ReadOnlyToolkit.execute()`, not the general legacy ToolRegistry/TurnEngine path. A model request for a legacy app, file, Raycast, browser or unknown tool is rejected rather than executed or silently granted permission.

For discovery, each legacy tool is individually classified as registered versus platform supported versus currently backed by its OS subprocess/path configuration. Mac-only `osascript` and `open` backends must not appear available on Windows/Linux. Python file tools can be platform-compatible but are unavailable for requested file operations without configured `allowed_paths`; each action still requires explicit Approval and target-specific safety checks. The 18 V2 catalog descriptions do **not** mean their separate provider layer is wired to the current production TurnEngine. No installed-application scan or private-file enumeration is performed.

## Model tool selection and streaming

Ollama's `/api/chat` documents structured `message.tool_calls` in streaming mode and a follow-up with assistant tool request and tool result ([Ollama Tool calling](https://docs.ollama.com/capabilities/tool-calling)). The configured Qwen2.5 family advertises tool support, but **native behavior on the user's exact local Ollama/model build is NOT MEASURED**.

The normal conversation request includes the two small tool descriptions but otherwise uses **one already-existing streaming Ollama call** with the same persona and session-limited history, including the current user turn exactly once. The first genuine token still streams immediately.

When Ollama *chooses* one of those two functions, the transport captures one native tool call; Python strictly validates name and empty arguments, executes **one** local read-only lookup, feeds the structured JSON result back as an assistant tool call + tool result, then performs exactly **one** additional streaming Ollama call with **no** tools supplied. There are no general tool loops, shell/code execution, extra model selectors on greeting, parallel OS actions, new messages persisted as tool commands, or changed WebSocket/voice events.

A narrowly scoped **integrity guard** recognizes obvious *live* clock/date or toolkit-capability inquiries. It does **not** write the answer or choose the final prose: it only requires the model to request the corresponding real data source. If the model attempts to invent a current time/capability summary without a valid tool call (or mixes unverified text with a tool call), the response fails visibly as an LLM/tool error, rather than publishing a guessed time or unsupported capabilities. A model/runtime that lacks reliable tool calling may therefore be unable to answer these fact questions until the tool path is supported; this is safer than fabricating live observations.

`system.local_datetime` and `toolkit.capability_snapshot` are the ONLY actions allowed for automated read-only execution; no generic `requires_approval=False` bypass was added.

## Test cases and performance evidence

Mocked end-to-end messages include `Hallo, Jarvis`, `Danke, Jarvis`, `Bist du da?`, `Okay`, ordinary follow-ups, local date/time and `Welche Systemfunktionen kannst du gerade verwenden?`. Tests assert model-supplied final text changes with the model, genuine same-session history/current-user-once, single normal stream, actual timezone-aware frozen Toolkit data reaching the second Ollama request, and zero legacy actions or approvals from discovery. Model failures, missing required tool calls, malformed/unknown/multiple/mixed calls and arguments are error outcomes, not false final replies.

Existing full routing, profile/session memory, semantic-pilot, YJVOICE-01, reminder, Safety/Approval, Windows packaged-startup and desktop tests stay enabled. Timing results represent *controlled structural ordering and model invocation counts*, **not** a real end-user latency benchmark. On the mocked paths: normal chat = **1 LLM request**; read-only fact query = **2 LLM requests and at most 1 read-only toolkit lookup**. Real CPU/GPU/Whisper/Ollama/mic latency **NOT MEASURED**, and LLM-first greeting can be slower than the former Python string. The first token remains streamed without an artificial Python preamble.

## Scope, limits and rollback

No new dependency, provider wiring, V2 domain contract change, DB migration, OS capability scanner, Voice/Wake/VAD/Whisper/TTS change, new language-model provider or autonomous planner. Native tool-call compatibility and spoken response quality on Windows/macOS must be tested on actual hardware (CI is headless). A file or app may still require device permission, OS-specific installation and approval even when its backend is present. Provider availability is not authorization.

Rollback: revert only this PR's merge commit after external approval, retaining all user data, profiles, learned commands, session history, models and existing YJVOICE/YJCOM functionality. External ChatGPT code review required: **STOP after green PR CI/Wiki and published-diff inspection; no self-merge**.
