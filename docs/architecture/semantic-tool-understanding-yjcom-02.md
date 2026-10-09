# YJCOM-02 — Safe Semantic Tool Understanding Pilot

## Baseline and scope

Started from YJCOM-01 merged main `2374d4d5bb0636a36faf0df94a10b3e5b18e079d`; post-merge CI 7/7 and Wiki published. This patch **does not** implement the V2 architecture, new OS providers, new tools, new database migrations, or an autonomous agent.

The legacy safety check, learning stage, deterministic local replies, complete existing heuristic catalog, ToolRegistry, durable Approval, WebSocket run IDs, Voice queue and TTS are retained.

## Existing boundary and pilot behavior

Before YJCOM-02, setting `JARVIS_ENABLE_TOOL_PLANNER=1` enabled the old optional LLM planner, which returned only a bool-style tool suggestion with limited registry checks. It could accept a registered but unsafe, ungrounded tool input. The flag remains **OFF by default** and now selects a bounded, typed **Semantic-Pilot** instead of the previous unvalidated model-to-tool fallback.

The existing fast route stays first: **Safety → learned command → local fast paths → deterministic heuristic → optional semantic interpretation → ToolRegistry → Approval → execution only after approval.**

A semantic model call occurs only for an explicit unresolved computer action, with the flag enabled, and **only on macOS**, where the current legacy tools can actually execute. The current five pilot tools all depend on AppleScript or the macOS `open` command. The current Windows code does **not** have equivalent legacy providers; even when the flag is enabled there, the pilot does not advertise these unsupported tools or invoke its semantic planner. This must not be confused with Windows read-only provider prototypes that have no legacy execution wiring. Normal text/Voice conversation remains available.

### Fixed allowlist and real validators

Exactly five tools are proposed to the model, never the whole registry:

| Tool | Accepted fields | Grounding/platform rule |
| --- | --- | --- |
| `open_app` | exactly `app_name: str` | Explicit, exact app name present in current user request (80 chars max), no injected paths |
| `open_url` | exactly `url: str` | Exact user-given URL, http/https, valid host, no credentials/control chars |
| `reminder_list` | optional `limit: int` | Explicit reminders-list action; default 8 or user-supplied bounded integer |
| `calendar_list_events` | optional `days_ahead: int`, `limit: int` | Explicit events-list action; defaults 7/10, new quantities must appear in the request |
| `notes_search` | `query: str`, optional `limit: int` | Exact user-mentioned search phrase, bounded query, explicit notes search |

Every proposal must name a registered tool whose existing `requires_approval` is true. Python validates the complete JSON object, every key, each type, and the user-provided target. Legacy `input_schema` is **not** assumed to be JSON Schema. No model-selected file writes, sending messages, Raycast command deeplinks, shell commands, reminder creation, or arbitrary tool chaining are supported. Model-suggested tools **do not** undergo adaptive rewriting into a nonallowlisted tool. Normal deterministic/learned legacy behavior is not restricted by this pilot allowlist.

Model output must be one small exact JSON object: `{"decision":"tool","tool_name":"...","tool_input":{...}}`, `{"decision":"clarify","question":"One concise question?"}` or `{"decision":"conversation"}`. Reject mixed prose, Markdown fences, duplicate keys, invalid/nonfinite JSON, unknown decisions and unexpected fields; do not log model reasoning. One non-streaming model request with a bounded 8-second Ollama read timeout and 9-second outer deadline. Malformed/error/timeout results are non-actions; ambiguous explicit instructions retain the normal clarification. Cancellation propagates. There is no additional LLM request on the default or deterministic paths.

### Tested example interpretation (with fake LLM; **not real device execution**)

- "Aktiviere bitte die App Safari" → model proposes `open_app(app_name="Safari")` → Python accepts because Safari is explicitly in the request → **approval_required**, not execution.
- "Gehe zu https://example.org/info" → model proposes that *exact* URL → **approval_required**; a different URL is rejected.
- "Zeig mir meine Notizen zu Projekt Phoenix" → model proposes `notes_search(query="Projekt Phoenix")` → **approval_required**; a made-up query is rejected.
- The same command plus a fabricated app, unsupported tool name, unexpected argument, invalid JSON or timeout → no approval.
- "Danke, Jarvis", "Wie spät ist es?", ordinary questions, already recognized tools and `/tool unknown` → **no semantic LLM call**.

## Pending clarification — reminder only

A bounded, process-local, **one-per-session** record is created only after an unambiguous existing reminder clarification:

- "Erinnere mich an den Einkauf." → "Wann soll ich dich daran erinnern?" → "Morgen um 10 Uhr." → assembled `reminder_create(title="Einkauf",due_at="<verified ISO>")` → normal **Approval**.
- "Mach mir morgen um 10 Uhr eine Erinnerung." → "Woran soll ich dich erinnern?" → "An den Einkauf." → the same verified intent → normal **Approval**.
- "Morgen früh" / time without an explicit day / invalid time → one targeted clarification, **no action**.
- "Abbrechen" → clear pending, **no action**.
- "Ach egal, erklär mir lieber Python" or a new computer/learned command → discard the pending reminder, process the new request normally.
- Different session, expired entry (120 seconds), process restart, or eviction beyond 32 sessions → **no cross-session completion**.

The original content/time come only from user-supplied utterances, not model-invented fields. The assembled request is **checked again by the existing Safety stage**, then sent to the ordinary persistent Tool Approval. A pending clarification itself never invokes `ToolRegistry.execute`.

Caveats: The in-memory clarification is intentionally not a durable multi-session state machine. It may be lost on restart. It requires explicit, valid day *and* clock time rather than guessing a default hour. The current reminder execution is a macOS `osascript` legacy tool; a Windows approval does not imply supported Windows reminder execution.

## How to activate the opt-in pilot

Developer macOS shell from the repository root, with dependencies already installed and Ollama configured:

```bash
JARVIS_ENABLE_TOOL_PLANNER=1 npm run dev
```

This is the existing `npm run dev` local development stack, and the process inherits `JARVIS_ENABLE_TOOL_PLANNER` through the Node launcher. Deactivate by removing the variable or setting `JARVIS_ENABLE_TOOL_PLANNER=0`; normal/default operation is OFF. On Windows there is currently no semantic execution pilot because the allowlisted legacy tools are macOS-only. No new UI toggle, installer configuration or undocumented flag was introduced.

## Test boundaries, remaining risk and rollback

No native macOS AppleScript/microphone/LLM timing is guaranteed by CI. Integration tests replace LLM responses, and never execute real OS commands. Windows and Linux CI verify that imports and packaging remain working; full GitHub Baseline CI / Wiki and test counts are recorded in PR handoff after actual runs.

Remain cautious: limited natural-language gating may still fail on untested phrasings; user-given but semantically misleading app/URL data still require human Approval. Time expressions outside the small deterministic reminder grammar require clarification, not guessing. Pending state is not concurrency-persistent or restart-persistent. Actual Ollama/Whisper latency: **NOT MEASURED** unless manually benchmarked.

To roll back a future authorized merge, revert only this pilot PR's commits, preserving private profiles, databases, messages, models, learning signals, Voice data and user workspace. Keep external review/STOP before merging.
