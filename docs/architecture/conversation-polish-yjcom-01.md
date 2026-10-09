# YJCOM-01 — Conversation Quick Polish

## Scope and baseline

Current production baseline: `main` at `8266ad3b1b6cd78107518421da708b772cf2baaf` (post-YJVOICE-01); initial baseline CI 7/7 and Wiki success. This is a small legacy interaction correction, not a V2 migration. There is no new dependency, model configuration, ToolRegistry, Policy, Approval, DB schema, TTS or Voice-capture change.

## Root causes found

1. The old `quick_utility_reply` matched words with `hint in lowered`; `date` in `datei` gave a date, and `jarvis` in an App command gave a fake readiness/health response. This preempted actual tool heuristics.
2. The generic tool-request gate treated `datei` and `mach` as sufficient for *any* tool instruction. Thus discussion *about* files, or `Mach es kürzer`, could be diverted to a tool explanation instead of continuing the conversation.
3. Local thanks/greeting/acknowledgment templates included repeated honorifics, speculative system-health claims and pushy follow-up questions. The persisted default profile plus generated system prompt both mentioned Mac-only identity.
4. Prompt history was already supplied from the current session after the current user message was saved; no second current turn needed to be appended. However related memory search was global rather than session-scoped. Three independent read-only prompt reads were awaited sequentially.
5. The server delayed the first genuine LLM token behind the regular 8-char/20ms batch threshold until another token or completion arrived. The UI already buffers WS tokens for 32ms and TTS waits for meaningful chunks; those bounds stay unchanged.

## Changes

- Exact, finite natural-language patterns for local time/date/readiness; limited command-verb and meta-question detection. Actual App/file/reminder requests remain eligible for the existing heuristics and explicit Approval. Unknown explicit `/tool` syntax cannot fall through to a different suggested tool via the optional LLM planner.
- Short natural templates: "Gerne.", "Hallo! Wie kann ich helfen?", "Alles klar." Readiness claims only presence, not unverified device/agent health. Incomplete reminders ask for **one missing detail**.
- Default persona is OS-neutral and guides short/factual replies and direct action reporting. Old *exact shipped* Mac-only default instructions are modernized **only in memory**. Custom identity/style/safety data and all existing `jarvis_profile.json` bytes remain unchanged.
- The existing same-session message history is the source of prior turns, and the current persisted user turn is not appended again. Memory retrieval now accepts an optional `session_id` and prompt recall scopes to that session; old callers without a session argument retain existing API behavior and DB schema.
- `asyncio.gather` overlaps three independent read-only SQLite calls (history, scoped memory and local tool statistics) without changing content or model calls. The first actual Ollama streaming token is delivered immediately; later tokens retain current batching, TTS chunking, and echo-suppression.

## Test evidence and performance interpretation

Targeted regressions cover `Jarvis, öffne Safari`, `Lies diese Datei`, `datei lesen /tmp/test.txt`, `Welches Datum haben wir?`, `Wie spät ist es?`, `Bist du da?`, discussion vs action, unknown `/tool`, safety/learned-command priority, incomplete reminders, short thanks/acknowledgments, legacy/custom profile preservation, in-session follow-up and prompt-turn uniqueness, out-of-session memory exclusion, concurrent read start and true first-token streaming before the next token arrives. The existing Voice test and Windows installer suites are unchanged and remain required.

Controlled fixtures demonstrate that all three reads **start before any finishes**, and that a token event exists while a mocked LLM stream pauses before its second token. These are structural latency improvements, not evidence of a specific number of milliseconds on a real user's device. Actual local Ollama, Whisper and microphone response times: **NOT MEASURED**. No extra LLM request or changed Ollama parameters.

## Known limits and rollback

- Short follow-up understanding still depends on the local LLM's available session history and does not reconstruct unavailable or ambiguous references.
- Some unsupported natural commands will still require one clarification; no new intent engine is introduced.
- On actual slower systems, parallel DB query contention could reduce or erase the controlled-fixture latency improvement. It does not bypass safety/approval.
- No server-side conversation/recording data migration. Revert this PR's commits on a future merge if necessary; never delete user profiles, databases or local runtime assets.
- Windows/macOS native mic, TTS, app execution and physical OS automation are **NOT RUN** as part of this polish.

Next step after successful CI and final GitHub diff inspection: **external ChatGPT PR review**; no self-merge or autonomous follow-up.
