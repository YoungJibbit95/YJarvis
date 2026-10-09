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
- `toolkit.capability_snapshot`: a bounded, structured snapshot derived from the **active legacy `ToolRegistry.list_specs()`** and actual implementation/platform checks. The independent V2 catalog is deliberately **not imported or enumerated** into the legacy runtime: the snapshot explicitly identifies the separate V2 layer as unwired and exposes no V2 capabilities as executable.

There are exactly **two** read-only callable names. Both take a strictly empty argument object, are side-effect-free, and receive a narrowly coded no-approval exception **only** in `ReadOnlyToolkit.execute()`, not the general legacy ToolRegistry/TurnEngine path. A model request for a legacy app, file, Raycast, browser or unknown tool is rejected rather than executed or silently granted permission.

For discovery, each legacy tool is individually classified as registered versus platform supported versus currently backed by its OS subprocess/path configuration. Mac-only `osascript` and `open` backends must not appear available on Windows/Linux. Python file tools can be platform-compatible but are unavailable for requested file operations without configured `allowed_paths`; each action still requires explicit Approval and target-specific safety checks. The independent 18-spec V2 catalog is a planning contract, but existing domain-isolation tests forbid a legacy import of that catalog. We keep those boundaries: the active snapshot does not enumerate V2 specs, explicitly flags `catalog_enumerated=false`, and reports no wired V2 execution capabilities. No installed-application scan or private-file enumeration is performed.

## Model tool selection and streaming

Ollama's `/api/chat` documents structured `message.tool_calls` in streaming mode and a follow-up with assistant tool request and tool result ([Ollama Tool calling](https://docs.ollama.com/capabilities/tool-calling)). The configured Qwen2.5 family advertises tool support, but **native behavior on the user's exact local Ollama/model build is NOT MEASURED**.

Normal conversation uses **one existing streaming Ollama call without tool declarations**, with the same persona and session-limited history and the current user turn exactly once. Only an identified live-fact question offers the two small read-only tool declarations; its first pass is withheld until verified. Ordinary chat still streams its first genuine token immediately.

When Ollama *chooses* one of those two functions, the transport captures one native tool call; Python strictly validates name and empty arguments, executes **one** local read-only lookup, feeds the structured JSON result back as an assistant tool call + tool result, then performs exactly **one** additional streaming Ollama call with **no** tools supplied. There are no general tool loops, shell/code execution, extra model selectors on greeting, parallel OS actions, new messages persisted as tool commands, or changed WebSocket/voice events.

A narrowly scoped **integrity guard** recognizes obvious *live* clock/date or toolkit-capability inquiries. It does **not** write the answer or choose the final prose: it only requires the model to request the corresponding real data source. If the model attempts to invent a current time/capability summary without a valid tool call (or mixes unverified text with a tool call), the response fails visibly as an LLM/tool error, rather than publishing a guessed time or unsupported capabilities. A model/runtime that lacks reliable tool calling may therefore be unable to answer these fact questions until the tool path is supported; this is safer than fabricating live observations.

`system.local_datetime` and `toolkit.capability_snapshot` are the ONLY actions allowed for automated read-only execution; no generic `requires_approval=False` bypass was added.

## External review corrections — PR #39

**HIGH-01: verified facts before any WebSocket/TTS tokens.**
The previous provenance gate recognized only a few time/date/toolkit formulations, so an ordinary native-tool-enabled model stream could publish a false fact before a later valid tool call was seen. The corrected path has two explicitly bounded modes:

- **Fact-sensitive request:** A small conservative intent-to-fact-source guard recognizes both the original variants and natural wording such as "Welche Programme kannst du auf diesem Rechner tatsächlich bedienen?", "Welche Anwendungen stehen dir hier zur Verfügung?", "Was kann dein Toolkit auf diesem Betriebssystem?", "Sag mir die aktuelle lokale Uhrzeit." and "Wie viel Uhr ist gerade auf meinem PC?". It chooses **only which real fact source is mandatory**, never a prewritten Python answer. Only such a first-pass request receives Ollama's native read-only toolkit tool declarations. Its content is withheld from ALL WebSocket token events (and therefore from downstream TTS) until the single requested tool call is validated. Any mixed tool-plus-text, missing tool, wrong tool or invalid argument **fails visibly without publishing its unverified text**. A correct single verified tool call is followed by one existing streamed LLM answer, with actual structured facts in the prompt.
- **Ordinary chat:** The single streaming model call has **no tools offered**, so no tool-decision round is entered; greeting/thanks/normal conversation still emit their first token early without a second model request. An unsolicited native tool call in this mode is rejected, not executed. This is an integrity boundary, not an attempt to generate smalltalk in Python.

No finite vocabulary gate guarantees classification of every conceivable paraphrase or stops unrelated spontaneous model hallucinations in ordinary discussion. Ambiguous or unrecognized fact questions may still fail model reliability expectations; additional language coverage requires future evidence/review, not a new static-answer table. The safeguard is explicitly an OS-fact provenance gate for recognizable **current/local** time and toolkit availability, not universal factual correctness of the LLM.

**MEDIUM-01: genuine per-implementation backend requirements.**
Capability snapshot is still derived from the actually registered legacy instances, not a second list of advertised OS tools. Backend requirements are explicitly associated with the existing system tool *classes*: \`open\` for app/URL/Raycast, \`pbpaste\` for clipboard read, \`pbcopy\` for clipboard write; the AppleScript implementations still check \`osascript\`. Unrecognized new system implementation classes are **unavailable until individually verified**. Mac-only OS commands remain unavailable on Windows regardless of which executables happen to be on PATH. Presence of a CLI is only a backend prerequisite, **not proof** of target-app installation or OS permissions. The snapshot never executes legacy tools, imports the isolated V2 Domain or scans the user's installed apps/private files.

**LOW-01: exactly one native read-only model call.**
A dict-valued \`arguments\` object represents a **complete** native call. More than one complete object is rejected even if its name and argument dict are identical, whether in the same streamed packet or separate packets. One call whose arguments are legitimately split into string fragments continues to be supported; multiple distinct calls or concatenated full JSON documents fail. No model tool call reaches legacy execution.

Focused end-to-end regression tests inspect real \`token\`, \`message\`, \`run_state\` event order: no false text is published before failure; successful verified model answers still stream; a greeting emits its first token before the next model chunk and uses one model call. Full Python, startup, desktop, Windows packaging and Wiki checks are required again on the final correction head.

## Test cases and performance evidence

Mocked end-to-end messages include `Hallo, Jarvis`, `Danke, Jarvis`, `Bist du da?`, `Okay`, ordinary follow-ups, local date/time and `Welche Systemfunktionen kannst du gerade verwenden?`. Tests assert model-supplied final text changes with the model, genuine same-session history/current-user-once, single normal stream, actual timezone-aware frozen Toolkit data reaching the second Ollama request, and zero legacy actions or approvals from discovery. Model failures, missing required tool calls, malformed/unknown/multiple/mixed calls and arguments are error outcomes, not false final replies.

Existing full routing, profile/session memory, semantic-pilot, YJVOICE-01, reminder, Safety/Approval, Windows packaged-startup and desktop tests stay enabled. Timing results represent *controlled structural ordering and model invocation counts*, **not** a real end-user latency benchmark. On the mocked paths: normal chat = **1 LLM request**; read-only fact query = **2 LLM requests and at most 1 read-only toolkit lookup**. Real CPU/GPU/Whisper/Ollama/mic latency **NOT MEASURED**, and LLM-first greeting can be slower than the former Python string. The first token remains streamed without an artificial Python preamble.

## Scope, limits and rollback

No new dependency, provider wiring, V2 domain contract change, DB migration, OS capability scanner, Voice/Wake/VAD/Whisper/TTS change, new language-model provider or autonomous planner. Native tool-call compatibility and spoken response quality on Windows/macOS must be tested on actual hardware (CI is headless). A file or app may still require device permission, OS-specific installation and approval even when its backend is present. Provider availability is not authorization.

Rollback: revert only this PR's merge commit after external approval, retaining all user data, profiles, learned commands, session history, models and existing YJVOICE/YJCOM functionality. External ChatGPT code review required: **STOP after green PR CI/Wiki and published-diff inspection; no self-merge**.
