# YJarvis V2 — Rescue Architecture, Migration Plan & Browser-Agent Master Prompt

**Repository:** `YoungJibbit95/YJarvis`  
**Target platform:** macOS / Apple Silicon  
**Baseline branch:** `main`  
**Verified baseline commit:** `dea0e9e6a266584e9c8efaf53dd82138aecbd662`  
**Document purpose:** Source of truth for rescuing YJarvis without a destructive rewrite  
**Execution model:** Browser-based development agent with direct GitHub access, one isolated PR at a time, mandatory external review before the next step  
**Primary constraint:** No Codex usage. No autonomous multi-PR implementation. No stacking unfinished work.

---

# 0. Executive decision

YJarvis should **not** be rewritten from scratch.

The existing project already contains valuable foundations:

- local-first architecture,
- FastAPI backend,
- Electron + React desktop application,
- SQLite persistence,
- Ollama integration,
- local STT and TTS,
- a tool registry,
- explicit safety concepts,
- streaming events,
- learned routines,
- macOS automation.

The project stalled because too many product layers were introduced at once and central modules accumulated too many responsibilities. The rescue therefore has one rule above all others:

> **Separate responsibilities before adding capabilities.**

The target is not “more features”. The target is a stable personal operating agent architecture in which new capabilities can be added without increasing global complexity.

The future YJarvis is defined as:

> **A private, local-first personal operating agent for macOS that listens, understands goals, plans actions, applies a transparent trust policy, executes local tools, remembers useful context, learns routines, and becomes progressively more autonomous only where the user has earned confidence in it.**

The core product qualities are:

1. **Natural** — users speak in normal language.
2. **Fast** — common actions feel immediate.
3. **Capable** — the assistant changes real system state instead of only talking.
4. **Continuous** — context, preferences and routines survive sessions.
5. **Trustworthy** — autonomy is proportional to risk and learned trust.
6. **Inspectable** — every action can be understood and audited.
7. **Local-first** — privacy and offline capability remain first-class.

---

# 1. Current-state diagnosis

This document assumes the current repository state around the verified baseline commit.

## 1.1 Current architecture

Current high-level stack:

- `apps/agent`
  - Python
  - FastAPI
  - SQLite through `aiosqlite`
  - Ollama HTTP API
  - whisper.cpp subprocess integration
  - Piper / `say` TTS
  - macOS AppleScript and system tools
- `apps/desktop`
  - Electron
  - React
  - TypeScript
  - WebSocket + HTTP communication to local agent
- `packages/shared-types`
  - basic TypeScript DTOs
- `runtime`
  - local DB, models, profile
- `tests`
  - Python unit tests focused on intent parsing, audio helpers and safety

## 1.2 Main architectural problems

### A. `AgentService` is an orchestration monolith

`apps/agent/jarvis_agent/agent_service.py` currently owns too many responsibilities:

- conversation state,
- profile loading,
- safety pre-checks,
- confirmation state,
- learning commands,
- quick replies,
- quick status responses,
- utility responses,
- clarification decisions,
- intent routing,
- learned-command routing,
- LLM planner fallback,
- approval creation,
- tool execution,
- tool-learning telemetry,
- LLM streaming,
- message persistence,
- event emission,
- memory compaction.

This means a small conversation change can affect safety, planning, tools and persistence simultaneously.

### B. Natural-language understanding is becoming a hand-written parser

`tool_intent.py` is already very large and contains extensive regex/heuristic logic for:

- apps,
- reminders,
- calendar,
- notes,
- contacts,
- messaging,
- Raycast,
- temporal expressions,
- titles,
- durations.

`conversation_helpers.py` adds another layer of regular-expression based interpretation.

Heuristics are useful as **fast paths**, but should not be the primary semantic architecture.

### C. The current action model can represent only one action

The existing routing model effectively produces:

```text
message -> zero or one ToolCallIntent
```

That blocks the central future capability:

```text
goal -> plan -> multiple dependent actions
```

A real operating agent must support:

> “Open my project notes, create a meeting tomorrow at 10, and remind me one hour before.”

This requires a first-class `ActionPlan`.

### D. Safety is over-conservative at the interaction layer

The tool metadata already contains useful concepts such as:

- `risk_level`,
- `requires_approval`.

But all registered tools currently request approval, including low-risk/read-only actions.

The user experience therefore becomes:

```text
request -> detect tool -> approval screen -> click -> execute
```

That is safe but not assistant-like.

The system needs a centralized policy engine capable of:

- auto-allow,
- allow with audit,
- ask for confirmation,
- block.

### E. Frontend state has become an implicit state machine

`App.tsx` contains nearly all application behavior, including:

- session bootstrap,
- chat messages,
- streaming drafts,
- WebSocket reconnect,
- busy state,
- watchdogs,
- voice recording,
- VAD-like RMS analysis,
- wake-word handling,
- echo suppression,
- TTS queue,
- streaming speech chunking,
- approvals,
- settings,
- smart-home state,
- command palette,
- all main view rendering.

Many refs and flags collectively form a state machine but no explicit state machine exists.

### F. Voice latency is dominated by lifecycle overhead

The current voice path is approximately:

```text
MediaRecorder
-> detect silence
-> produce Blob
-> HTTP upload
-> write temp file
-> ffmpeg if needed
-> launch whisper.cpp process
-> transcribe
-> read transcript
-> intent routing
-> approval or LLM/tool
-> streaming response
-> TTS synthesis
-> playback
```

Repeated process startup and a long silence threshold make the experience feel slower than necessary.

### G. “Learning” is currently routines + execution statistics

The existing learning system is useful, but it is not yet general learning.

It currently provides mainly:

- learned trigger -> single tool mapping,
- success/failure counts,
- average latency,
- limited adaptive routing.

This should be retained but renamed conceptually to **Routines** and **Tool Performance Telemetry**.

### H. Memory is conversation compaction, not semantic memory

Current memory periodically copies recent conversation content into a memory table.

The target should instead distinguish:

- stable user preferences,
- people,
- projects,
- routines,
- corrections,
- durable facts,
- transient conversation context.

### I. Feature surface exceeds implemented depth

Smart Home already has:

- API,
- DB model,
- UI tab,

but currently uses a stub provider.

This increases maintenance surface without improving the core Jarvis experience.

---

# 2. Rescue principles

These principles are mandatory. Any future implementation that violates them requires an explicit architecture decision record.

## 2.1 No big-bang rewrite

Legacy behavior remains operational while replacements are introduced behind explicit interfaces and feature flags.

## 2.2 One responsibility per subsystem

No module should become the new version of `AgentService` or `App.tsx`.

## 2.3 Domain contracts first

Before implementation, define explicit domain types for:

- turns,
- plans,
- actions,
- policy decisions,
- tool requests,
- observations,
- memories,
- routine matches,
- events.

## 2.4 Planning and execution are separate

The planner is never allowed to execute tools.

The executor is never allowed to invent new goals.

## 2.5 Policy sits between plan and execution

No action reaches a tool without a policy decision.

## 2.6 Read-only and side-effect actions are different

The system must distinguish observation from mutation.

## 2.7 Common operations get fast paths

Do not route every trivial task through an LLM.

Examples:

- exact learned routine,
- open known app,
- simple clipboard read,
- local system status,
- current date/time.

But fast paths must produce the **same domain action format** as the planner.

## 2.8 Natural language is not a regex product surface

Regex is acceptable for:

- strict command syntax,
- normalization,
- wake word,
- a small number of deterministic shortcuts.

Regex must not become the long-term primary language-understanding system.

## 2.9 User trust is explicit state

Autonomy must be based on:

- tool risk,
- action type,
- target,
- user policy,
- historical reliability,
- current plan context.

## 2.10 Observability is a feature

Every turn should be inspectable as:

```text
input
-> route
-> plan
-> policy
-> execution
-> observation
-> response
```

## 2.11 Performance must be measured, not guessed

Latency metrics become first-class.

## 2.12 Every migration step must be reversible

Every PR must leave `main` in a usable state.

---

# 3. Target architecture

## 3.1 Logical architecture

```text
                    ┌───────────────────────────────┐
                    │         Desktop UI            │
                    │ Chat / Voice / Inline Consent │
                    └───────────────┬───────────────┘
                                    │
                          HTTP / WebSocket / IPC
                                    │
                    ┌───────────────▼───────────────┐
                    │        Input Gateway           │
                    │ text / voice transcript        │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │          Turn Engine           │
                    │ lifecycle + orchestration      │
                    └──────┬────────┬────────┬──────┘
                           │        │        │
            ┌──────────────▼┐  ┌────▼─────┐  ┌──────────────▼┐
            │ Context Engine │  │ Router   │  │ Routine Store │
            │ session/memory │  │          │  │ exact habits  │
            └───────────────┘  └────┬─────┘  └───────────────┘
                                    │
                        ┌───────────▼───────────┐
                        │      Plan Builder      │
                        │ ActionPlan + steps     │
                        └───────────┬───────────┘
                                    │
                        ┌───────────▼───────────┐
                        │      Policy Engine     │
                        │ allow / confirm / deny │
                        └───────────┬───────────┘
                                    │
                        ┌───────────▼───────────┐
                        │      Plan Executor     │
                        │ dependencies + status  │
                        └───────────┬───────────┘
                                    │
                        ┌───────────▼───────────┐
                        │      Tool Runtime      │
                        │ macOS / files / apps   │
                        └───────────┬───────────┘
                                    │
                        ┌───────────▼───────────┐
                        │      Observations      │
                        │ normalized results     │
                        └───────────┬───────────┘
                                    │
                 ┌──────────────────▼──────────────────┐
                 │ Response Composer / Memory Commit   │
                 └──────────────────┬──────────────────┘
                                    │
                           text stream / TTS
```

---

# 4. Target backend package layout

Target structure:

```text
apps/agent/jarvis_agent/
├── api/
│   ├── app.py
│   ├── dependencies.py
│   ├── routes/
│   │   ├── health.py
│   │   ├── sessions.py
│   │   ├── turns.py
│   │   ├── approvals.py
│   │   ├── settings.py
│   │   └── audio.py
│   └── websocket.py
│
├── domain/
│   ├── turn.py
│   ├── plan.py
│   ├── action.py
│   ├── policy.py
│   ├── observation.py
│   ├── memory.py
│   ├── routine.py
│   └── events.py
│
├── orchestration/
│   ├── turn_engine.py
│   ├── router.py
│   ├── plan_builder.py
│   ├── plan_executor.py
│   ├── response_composer.py
│   └── context_builder.py
│
├── planning/
│   ├── structured_planner.py
│   ├── fast_paths.py
│   ├── schemas.py
│   └── validation.py
│
├── policy/
│   ├── engine.py
│   ├── rules.py
│   ├── trust.py
│   └── path_policy.py
│
├── tools/
│   ├── base.py
│   ├── registry.py
│   ├── runtime.py
│   ├── macos/
│   │   ├── apps.py
│   │   ├── clipboard.py
│   │   ├── reminders.py
│   │   ├── calendar.py
│   │   ├── notes.py
│   │   ├── contacts.py
│   │   ├── mail.py
│   │   ├── messages.py
│   │   ├── music.py
│   │   └── raycast.py
│   └── files/
│       ├── read.py
│       └── write.py
│
├── memory/
│   ├── service.py
│   ├── extraction.py
│   ├── retrieval.py
│   └── ranking.py
│
├── routines/
│   ├── service.py
│   ├── matcher.py
│   └── metrics.py
│
├── voice/
│   ├── service.py
│   ├── stt.py
│   ├── tts.py
│   ├── normalization.py
│   └── tempfiles.py
│
├── persistence/
│   ├── database.py
│   ├── migrations/
│   │   ├── 001_baseline.sql
│   │   ├── 002_turns_plans.sql
│   │   ├── 003_memories_v2.sql
│   │   └── ...
│   └── repositories/
│       ├── sessions.py
│       ├── messages.py
│       ├── turns.py
│       ├── plans.py
│       ├── approvals.py
│       ├── memories.py
│       ├── routines.py
│       ├── settings.py
│       └── tool_runs.py
│
├── llm/
│   ├── client.py
│   ├── ollama.py
│   ├── prompts.py
│   └── json_repair.py
│
├── observability/
│   ├── metrics.py
│   ├── tracing.py
│   └── diagnostics.py
│
├── config.py
└── bootstrap.py
```

This is a target structure, not a requirement to move everything in one PR.

---

# 5. Core domain model

## 5.1 Turn

A **Turn** is the atomic user interaction lifecycle.

```python
Turn {
    id: UUID
    session_id: UUID
    input_mode: "text" | "voice"
    user_text: str

    state:
        "received"
        | "context_building"
        | "routing"
        | "planning"
        | "awaiting_confirmation"
        | "executing"
        | "responding"
        | "completed"
        | "failed"
        | "cancelled"

    created_at: datetime
    updated_at: datetime
}
```

Rules:

- one user submission creates one turn;
- one turn may contain zero, one or many actions;
- a turn can pause for confirmation;
- a turn can resume later without losing plan state;
- a turn may produce multiple execution observations;
- UI status derives from turn state, not scattered booleans.

## 5.2 Action

An action is a normalized capability request.

```python
Action {
    id: UUID
    capability: str
    arguments: dict
    mode: "read" | "write" | "external_side_effect" | "system"
    risk: "low" | "medium" | "high" | "critical"
    reversible: bool
    requires_result: bool
}
```

Example:

```json
{
  "id": "a1",
  "capability": "calendar.create_event",
  "arguments": {
    "title": "Projekt Review",
    "start_at": "2026-10-08T10:00:00+02:00",
    "duration_minutes": 30
  },
  "mode": "write",
  "risk": "medium",
  "reversible": true,
  "requires_result": true
}
```

## 5.3 ActionPlan

```python
ActionPlan {
    id: UUID
    turn_id: UUID
    goal: str
    summary: str
    actions: list[PlannedAction]
    status:
        "draft"
        | "validated"
        | "awaiting_confirmation"
        | "approved"
        | "executing"
        | "completed"
        | "failed"
        | "cancelled"
}
```

`PlannedAction` adds dependency information:

```python
PlannedAction {
    action: Action
    depends_on: list[UUID]
    on_failure: "stop" | "continue" | "ask_user"
}
```

Example:

```text
Goal:
Prepare tomorrow's project review.

Step 1:
Read project note.

Step 2:
Create calendar event.
Depends on: none.

Step 3:
Create reminder one hour before event.
Depends on: step 2.

Step 4:
Compose final response.
Depends on: steps 1-3.
```

## 5.4 Observation

Every tool returns a normalized observation.

```python
Observation {
    action_id: UUID
    success: bool
    summary: str
    data: dict
    error_code: str | null
    error_detail: str | null
    duration_ms: int
    occurred_at: datetime
}
```

Tools should not generate conversational prose beyond a concise machine-readable summary.

## 5.5 PolicyDecision

```python
PolicyDecision {
    action_id: UUID
    verdict: "allow" | "confirm" | "deny"
    reason_code: str
    human_reason: str
    policy_source: str
}
```

## 5.6 ConfirmationBundle

When multiple actions require confirmation, they should be grouped where safe.

```python
ConfirmationBundle {
    plan_id: UUID
    action_ids: list[UUID]
    title: str
    description: str
    consequences: list[str]
    expires_at: datetime | null
}
```

Example UI:

> Jarvis wants to:
> - create “Projekt Review” tomorrow at 10:00;
> - create a reminder at 09:00.
>
> Approve both?

One approval. Not two separate tabs and clicks.

---

# 6. Turn Engine

`TurnEngine` becomes the central orchestrator, but remains intentionally thin.

It coordinates services. It does not contain each service's implementation.

Pseudo-flow:

```python
async def process_turn(turn_id):
    turn = turns.load(turn_id)

    context = await context_builder.build(turn)
    route = await router.route(turn, context)

    if route.kind == "direct_response":
        return await responder.finish_direct(...)

    plan = await plan_builder.build(turn, context, route)
    plan = await plan_validator.validate(plan)

    policy_result = await policy_engine.evaluate(plan, context)

    if policy_result.requires_confirmation:
        await confirmation_service.pause_turn(...)
        return

    observations = await plan_executor.execute(plan, context)
    await memory_service.consider(turn, plan, observations)
    await responder.respond(turn, plan, observations)
```

TurnEngine rules:

- no regex parsing;
- no SQL;
- no direct subprocess calls;
- no UI-specific behavior;
- no tool-specific conditionals such as `if tool_name == "raycast"`;
- no direct AppleScript;
- no TTS implementation.

---

# 7. Router design

The Router chooses **how to understand the task**, not which exact implementation details to execute.

Priority:

```text
1. strict internal commands
2. exact routine match
3. deterministic fast path
4. structured planner
5. conversational response
```

## 7.1 Strict internal commands

Examples:

- `/learn`
- `/unlearn`
- `/routines`
- `/diagnostics`

Strict syntax is allowed to use deterministic parsers.

## 7.2 Routine match

A user-defined routine can map natural shorthand to a plan template.

Example:

```text
"fokusmodus"
- open project folder
- open Notes
- start focus timer
```

This is fundamentally more useful than mapping a trigger to one single tool.

## 7.3 Deterministic fast paths

Only high-confidence patterns should remain.

Examples:

- `öffne Safari`
- `wie spät ist es`
- `lies Zwischenablage`
- exact app aliases.

A fast path must produce an `ActionPlan`, not bypass architecture.

## 7.4 Structured planner

The planner receives:

- user request,
- minimal context,
- available capability schemas,
- current date/time if required,
- relevant memories,
- relevant routine hints.

It returns strict JSON conforming to a versioned schema.

No free-form parsing of arbitrary planner prose.

Example response:

```json
{
  "version": "1",
  "goal": "Create a reminder for tomorrow",
  "needs_clarification": false,
  "clarification_question": null,
  "actions": [
    {
      "id": "a1",
      "capability": "reminders.create",
      "arguments": {
        "title": "Licht ausmachen",
        "due_at": "2026-10-07T10:00:00+02:00"
      }
    }
  ]
}
```

Planner output is never trusted directly.

It must pass:

1. JSON schema validation;
2. capability existence validation;
3. argument validation;
4. policy enrichment;
5. dependency validation.

---

# 8. Tool architecture

## 8.1 ToolSpec V2

Replace loosely descriptive schemas with explicit metadata.

```python
ToolSpec {
    capability: str
    description: str
    input_model: PydanticModel
    output_model: PydanticModel | None

    mode:
        "read"
        | "write"
        | "external_side_effect"
        | "system"

    default_risk:
        "low"
        | "medium"
        | "high"
        | "critical"

    reversible: bool
    idempotent: bool
    supports_dry_run: bool
    timeout_seconds: float
}
```

## 8.2 Capability naming

Use namespaced capabilities:

```text
apps.open
url.open
clipboard.read
clipboard.write
reminders.create
reminders.list
calendar.create_event
calendar.list_events
notes.create
notes.search
mail.create_draft
messages.send
contacts.search
music.control
files.read
files.write
raycast.open
raycast.run_command
```

Avoid implementation names in planner prompts.

The planner should know **what** a capability does, not that it happens through AppleScript.

## 8.3 Tool Runtime

`ToolRuntime.execute(action)`:

1. resolve capability;
2. validate arguments;
3. create execution record;
4. apply timeout;
5. call tool;
6. normalize result;
7. emit observation event;
8. persist execution metrics.

## 8.4 Tool implementation isolation

The current large `applescript_tools.py` should eventually split by domain.

Each implementation module should be independently testable.

## 8.5 No approval logic inside tools

Tools execute already-authorized actions.

Policy belongs outside tool implementation.

---

# 9. Policy and trust engine

This is one of the most important YJarvis V2 components.

## 9.1 Verdicts

Every action receives exactly one verdict:

- `ALLOW`
- `CONFIRM`
- `DENY`

## 9.2 Baseline policy

Suggested initial policy:

| Action class | Default |
|---|---|
| local read-only, non-sensitive | allow |
| open app / open URL | allow |
| clipboard read | confirm initially if user considers clipboard sensitive; configurable |
| local reversible write | confirm |
| calendar/reminder creation | confirm initially |
| mail draft creation | confirm or allow based on policy |
| sending message/email | confirm |
| arbitrary file read | path + sensitivity policy |
| file write | confirm |
| system configuration | confirm/high risk |
| destructive/system-critical | deny |

The user can later promote selected actions to trusted automatic execution.

## 9.3 Trust scopes

Trust must be scoped, never global.

Examples:

```text
calendar.create_event
calendar.create_event on calendar "Personal"
files.write inside ~/Documents/YJarvis
messages.send to specific contact
apps.open any local app
```

## 9.4 Trust state

Suggested levels:

- `never`
- `ask`
- `trusted`
- `blocked`

Do not infer `trusted` from a single approval.

Future automatic trust suggestion may require:

- minimum successful executions;
- zero recent failures;
- reversible action;
- low/medium risk;
- explicit user opt-in.

## 9.5 Hard policy

Some actions must remain non-overridable.

Examples:

- destructive requests targeting system paths;
- attempts to disable security controls;
- unknown arbitrary privileged shell execution;
- tool arguments outside allowed path scopes.

## 9.6 Policy explanation

Every confirmation or denial must have a human explanation.

Bad:

> Approval required.

Good:

> This action will send a message to another person, so Jarvis requires your confirmation.

---

# 10. Multi-step execution

## 10.1 Dependency graph

Plans may be linear or DAG-like.

Initial implementation may restrict plans to a simple ordered list plus dependencies.

Avoid general workflow-engine complexity in V2.0.

## 10.2 Execution rules

For each step:

1. verify dependencies completed;
2. re-evaluate dynamic policy if needed;
3. execute;
4. persist observation;
5. decide failure behavior.

## 10.3 Failure strategies

Supported initially:

- `stop`
- `continue`
- `ask_user`

Examples:

- if app fails to open, stop;
- if optional note lookup fails, continue;
- if two contacts match “Alex”, ask user.

## 10.4 Cancellation

A turn awaiting confirmation must be cancellable.

An actively executing plan should support best-effort cancellation between steps.

Do not claim transactional rollback for external macOS applications unless actually implemented.

---

# 11. Context architecture

Context should be built for a turn from separate layers.

```text
ContextBundle
├── current session context
├── user preferences
├── relevant semantic memories
├── routine matches
├── tool-performance hints
├── environment facts
└── current date/time when necessary
```

Do not place all stored data into every LLM prompt.

Context selection is itself a service.

---

# 12. Memory V2

## 12.1 Memory types

At minimum:

```text
preference
person
project
routine_hint
fact
correction
working_context
```

## 12.2 Example records

Preference:

```json
{
  "type": "preference",
  "key": "preferred_notes_app",
  "value": "Notes",
  "confidence": 1.0
}
```

Person:

```json
{
  "type": "person",
  "key": "alex",
  "value": {
    "display_name": "Alex Example",
    "relationship": "project teammate"
  }
}
```

Correction:

```json
{
  "type": "correction",
  "key": "project_folder",
  "value": "~/Projects/YJarvis",
  "source_text": "Mit Projektordner meine ich immer ~/Projects/YJarvis"
}
```

## 12.3 Memory lifecycle

```text
candidate
-> extracted
-> validated
-> active
-> superseded/deleted
```

Do not silently convert every conversation into durable memory.

## 12.4 Memory provenance

Store:

- originating session/turn,
- source text hash or reference,
- creation time,
- confidence,
- last used,
- superseded-by relation.

## 12.5 Retrieval

SQLite FTS may remain the first implementation.

Do not introduce a vector database until measurements prove FTS insufficient.

A later hybrid retriever can combine:

- exact key matching,
- FTS,
- recency,
- importance,
- semantic embeddings.

## 12.6 User controls

Memory must be inspectable and removable.

Future UI:

```text
What Jarvis knows
- Preferences
- People
- Projects
- Routines
```

---

# 13. Routines

Rename the conceptual “learning engine” to routines + telemetry.

## 13.1 Routine model

```python
Routine {
    id
    trigger
    name
    plan_template
    enabled
    created_at
    updated_at
    usage_count
    success_count
    failure_count
}
```

## 13.2 Routine output

A routine should produce an `ActionPlan`.

It must not directly execute tools.

## 13.3 Backward compatibility

Existing `learned_commands` should migrate without data loss.

Legacy single-tool routine becomes:

```text
Routine
  -> ActionPlan with one Action
```

---

# 14. Voice architecture

Voice is a subsystem, not UI glue.

## 14.1 Voice flow

Target:

```text
microphone
-> input state machine
-> VAD/end-of-turn detection
-> STT service
-> normalized transcript
-> TurnEngine
-> streaming assistant text
-> sentence/chunk boundary
-> TTS queue
-> playback
-> microphone resumes
```

## 14.2 Explicit voice states

```text
off
arming
listening
speech_detected
finalizing
transcribing
awaiting_agent
speaking
suppressed
error
```

One state should be authoritative.

Avoid dozens of independent boolean refs.

## 14.3 Frontend voice service

Move browser audio lifecycle out of `App.tsx`.

Target hook/service:

```text
useVoiceSession()
```

Responsibilities:

- microphone permission,
- MediaStream lifecycle,
- VAD,
- segmentation,
- echo suppression coordination,
- upload,
- state reporting.

## 14.4 TTS manager

Separate:

```text
useTtsQueue()
```

Responsibilities:

- sentence chunking,
- ordering,
- cancellation,
- interrupt support,
- current playback state.

## 14.5 Persistent STT

The architecture should support multiple STT implementations through:

```python
class SttBackend(Protocol):
    async def transcribe(audio) -> Transcript:
        ...
```

First migration can retain the existing process backend.

A later PR should add a warm/persistent backend.

Possible implementations:

- persistent whisper.cpp server mode,
- long-lived local worker,
- compatible local STT runtime.

Do not hard-code future architecture to one whisper.cpp CLI version.

## 14.6 Wake word

Wake word and speech recognition are separate responsibilities.

Initial V2 may retain phrase-prefix detection.

Future dedicated wake-word engine is optional.

## 14.7 Voice performance targets

These are engineering targets, not promises. Measure on a defined Apple Silicon baseline before making them release gates.

Suggested warm-system goals:

- silence/end-of-turn detection: ~500–700 ms after speech end;
- short utterance STT: target sub-second median where hardware permits;
- fast-path routing: <250 ms;
- first streamed text token: target <1.5 s warm;
- TTS first audible chunk after usable sentence: target <700 ms;
- no full model reload on each voice turn.

Track p50 and p95.

---

# 15. LLM architecture

## 15.1 Provider boundary

Create:

```python
LlmClient
```

Operations:

- `stream_response(...)`
- `complete_structured(...)`

Ollama becomes one provider.

## 15.2 Structured planning

Use a dedicated low-temperature planner prompt with strict schema.

Do not mix persona wording and planning semantics.

## 15.3 Response model vs planner model

Architecture should permit different models but does not require it initially.

Example future:

- small fast model for tool planning;
- larger local model for complex conversation.

## 15.4 Prompt ownership

Prompts should live in dedicated files/modules.

Do not scatter system strings through services.

## 15.5 Planner fail-closed behavior

If structured output cannot be validated:

- do not execute;
- attempt one constrained repair if appropriate;
- otherwise ask user or fall back to conversational response.

Never guess tool arguments after validation failure.

---

# 16. Frontend target architecture

Target structure:

```text
apps/desktop/src/
├── app/
│   ├── App.tsx
│   ├── routes.ts
│   └── providers.tsx
│
├── api/
│   ├── client.ts
│   ├── turns.ts
│   ├── approvals.ts
│   ├── settings.ts
│   └── audio.ts
│
├── features/
│   ├── chat/
│   │   ├── ChatView.tsx
│   │   ├── MessageList.tsx
│   │   ├── Composer.tsx
│   │   └── useConversation.ts
│   │
│   ├── voice/
│   │   ├── VoiceOrb.tsx
│   │   ├── VoiceControls.tsx
│   │   ├── useVoiceSession.ts
│   │   └── useTtsQueue.ts
│   │
│   ├── approvals/
│   │   ├── InlineApproval.tsx
│   │   └── ApprovalHistory.tsx
│   │
│   ├── settings/
│   ├── diagnostics/
│   └── routines/
│
├── realtime/
│   ├── useJarvisSocket.ts
│   └── eventReducer.ts
│
├── state/
│   ├── turnReducer.ts
│   └── types.ts
│
├── components/
└── styles/
```

## 16.1 `App.tsx` target

`App.tsx` should eventually be mostly composition.

Rough goal:

- ideally <250 lines;
- no MediaRecorder implementation;
- no WebSocket reconnect implementation;
- no TTS queue implementation;
- no approval fetch implementation;
- no giant tab rendering functions.

Line count is not itself the goal; responsibility boundaries are.

## 16.2 Event reducer

Realtime events should flow through one reducer.

Example:

```text
TURN_RECEIVED
TURN_PLANNING
PLAN_READY
CONFIRMATION_REQUIRED
ACTION_STARTED
ACTION_COMPLETED
TURN_RESPONDING
TOKEN
TURN_COMPLETED
TURN_FAILED
```

## 16.3 Inline approval

Approvals should appear in conversation context.

The separate Approvals tab can remain as history/advanced view.

## 16.4 Developer diagnostics

Timeline and raw event state should become a diagnostics mode rather than primary surface.

---

# 17. Realtime event protocol V2

Version events.

```json
{
  "protocol_version": 2,
  "event": "action.completed",
  "turn_id": "...",
  "plan_id": "...",
  "action_id": "...",
  "timestamp": "...",
  "data": {}
}
```

Suggested events:

```text
turn.received
turn.context_ready
turn.routing
plan.created
plan.validated
policy.evaluated
confirmation.required
confirmation.resolved
action.started
action.completed
action.failed
response.started
response.token
response.completed
turn.completed
turn.failed
voice.state
```

Never require UI to infer state from textual `detail` messages.

---

# 18. Persistence V2

## 18.1 Migration system

Do not continue growing one large `CREATE TABLE IF NOT EXISTS` block forever.

Introduce migration bookkeeping:

```text
schema_migrations
- version
- applied_at
```

Migrations must be forward-only for normal app startup.

Development rollback may be supported separately.

## 18.2 Proposed new tables

### `turns`

```text
id
session_id
input_mode
user_text
state
created_at
updated_at
completed_at
error_code
```

### `plans`

```text
id
turn_id
goal
summary
status
created_at
updated_at
```

### `plan_actions`

```text
id
plan_id
position
capability
arguments_json
mode
risk
reversible
on_failure
status
```

### `action_dependencies`

```text
action_id
depends_on_action_id
```

### `observations`

```text
id
action_id
success
summary
data_json
error_code
error_detail
duration_ms
created_at
```

### `policy_decisions`

```text
id
action_id
verdict
reason_code
human_reason
policy_source
created_at
```

### `trust_rules`

```text
id
capability_pattern
scope_json
decision
created_at
updated_at
```

### `memories_v2`

```text
id
type
key
value_json
text_value
confidence
importance
source_turn_id
created_at
updated_at
last_used_at
superseded_by
```

### `routines`

```text
id
name
trigger
plan_template_json
enabled
usage_count
success_count
failure_count
created_at
updated_at
```

## 18.3 Existing data

Do not delete existing tables during early migration.

Introduce adapters.

Only remove legacy storage in a later dedicated cleanup PR after migration tests exist.

---

# 19. Error architecture

Do not surface arbitrary Python exceptions as product messages.

Use error codes.

Examples:

```text
STT_BACKEND_UNAVAILABLE
STT_MODEL_NOT_FOUND
LLM_UNAVAILABLE
LLM_TIMEOUT
PLAN_INVALID
PLAN_UNSUPPORTED_CAPABILITY
POLICY_DENIED
ACTION_TIMEOUT
ACTION_PERMISSION_DENIED
ACTION_TARGET_NOT_FOUND
DB_FAILURE
VOICE_PERMISSION_DENIED
```

Each error has:

- stable code,
- developer detail,
- user-facing summary,
- recoverability flag.

---

# 20. Observability

Local-first does not mean opaque.

Store local operational metrics.

## 20.1 Turn metrics

- total duration,
- context build duration,
- planning duration,
- policy duration,
- tool execution duration,
- response first-token latency,
- response total duration.

## 20.2 Voice metrics

- utterance duration,
- silence-to-finalize duration,
- STT duration,
- TTS synth duration,
- playback queue delay.

## 20.3 Tool metrics

Keep and improve current:

- success count,
- failure count,
- median/average latency,
- recent failure,
- timeout count.

## 20.4 Diagnostics export

Future diagnostics export should contain:

- versions,
- backend health,
- model configuration,
- timings,
- recent error codes,

but not dump sensitive message contents by default.

---

# 21. Security model

## 21.1 Principle of least capability

Tools should not receive broad system access if not required.

## 21.2 Path safety

Keep allowed path policy, but centralize it.

Canonicalize paths before policy decisions.

Protect against:

- `..`,
- symlink escapes,
- case/path normalization issues,
- system-root aliases.

## 21.3 Shell policy

Avoid generic shell execution capability in normal planner-visible tools.

Prefer narrow typed tools.

## 21.4 Secrets

Never:

- commit secrets,
- include secrets in planner prompts,
- expose keychain values in logs,
- store plaintext credentials in normal settings tables.

## 21.5 External side effects

Sending messages, mail or other external communication must remain explicit policy events.

## 21.6 Audit

Every mutation should have:

- turn id,
- plan id,
- action id,
- arguments,
- policy decision,
- result,
- timestamp.

Sensitive values may require redaction.

---

# 22. Testing strategy

Testing must become a central development accelerator.

## 22.1 Unit tests

Required for:

- domain validation,
- policy rules,
- plan validation,
- routine matching,
- memory extraction rules,
- path safety,
- error mapping.

## 22.2 Golden NLU / planning corpus

Create a test fixture containing realistic German instructions.

Categories:

- apps,
- reminders,
- calendar,
- notes,
- contacts,
- multi-step goals,
- ambiguity,
- dialect variants,
- malformed input,
- dangerous requests.

Example:

```yaml
- input: "Jarvis, öffne Safari."
  expected_capabilities:
    - apps.open

- input: "Mach morgen um zehn Projekt Review für 30 Minuten in den Kalender."
  expected_capabilities:
    - calendar.create_event

- input: "Öffne meine Projektnotiz und plane morgen um zehn ein Review."
  expected_capabilities:
    - notes.search
    - calendar.create_event
```

LLM-dependent tests should distinguish:

- deterministic schema tests,
- optional integration tests.

## 22.3 Policy matrix tests

Every registered capability must have policy coverage.

Test combinations:

- read/write,
- trusted/untrusted,
- sensitive/non-sensitive,
- allowed/disallowed path,
- low/high risk.

## 22.4 Tool contract tests

Tool implementations should be testable with subprocess adapters mocked.

## 22.5 API tests

FastAPI routes:

- sessions,
- turns,
- confirmation,
- settings,
- audio health.

## 22.6 Frontend tests

At minimum:

- event reducer,
- turn state reducer,
- approval display,
- voice state transitions,
- TTS queue logic.

## 22.7 End-to-end smoke scenarios

Define a small manual/macOS integration suite:

1. text chat response;
2. open Safari;
3. list reminders;
4. create reminder after confirmation;
5. voice -> transcript -> response;
6. multi-step plan;
7. denial of dangerous path operation.

---

# 23. CI and repository hygiene

The repository should gain GitHub Actions early.

Required checks:

```text
python-tests
python-lint
desktop-typecheck
desktop-build
```

Optional later:

```text
frontend-tests
integration-contract-tests
```

Use pinned or constrained runtime versions.

A PR is not review-ready until all available required checks are green.

No browser agent may claim “tests pass” unless it has actual evidence from:

- local execution it can show, or
- GitHub Actions/checks.

---

# 24. Branch and PR protocol

Every migration step receives exactly one branch and one PR.

Branch naming:

```text
yjv2/00-baseline-ci
yjv2/01-domain-contracts
yjv2/02-turn-engine-extraction
...
```

PR title:

```text
[YJ2-00] Establish baseline CI and architecture guardrails
```

PR body must contain:

```markdown
## Goal

## Scope

## Explicitly out of scope

## Files changed

## Behavioral changes

## Migration / compatibility

## Tests executed

## GitHub checks

## Manual verification

## Risks

## Rollback

## Review checklist

## Next step
BLOCKED until this PR is reviewed and accepted.
```

Never stack future migration work on an unreviewed PR.

---

# 25. Mandatory “stop gate”

After every PR:

1. push branch;
2. open PR;
3. wait for GitHub checks;
4. fix failures;
5. inspect the final diff;
6. write review summary;
7. stop all implementation work;
8. provide the PR URL to the user;
9. explicitly instruct:

> **Bitte diesen PR zuerst von ChatGPT gegen die YJarvis-V2-Architektur prüfen lassen. Ich beginne keinen weiteren Schritt, bis du mir nach dieser Prüfung ausdrücklich die Freigabe gibst.**

The browser agent must **not**:

- create the next branch,
- prepare the next PR,
- silently refactor unrelated code,
- merge the current PR,
- assume approval from CI.

Only explicit user instruction after external review unlocks the next migration step.

---

# 26. Migration roadmap

This roadmap is deliberately staged to reduce risk.

## PR 00 — Baseline, CI and architecture guardrails

### Goal

Create a trusted development baseline before architectural movement.

### Scope

- add GitHub Actions;
- run current Python tests;
- build/typecheck desktop;
- document exact supported setup;
- add architecture docs directory;
- add contribution/PR template if helpful;
- add no-behavior-change baseline diagnostics.

### Do not do

- do not refactor `AgentService`;
- do not change approvals;
- do not change voice behavior;
- do not change tools.

### Acceptance

- current test suite passes;
- desktop build passes;
- CI runs automatically on PR;
- no product behavior intentionally changes.

### Stop gate

Mandatory external review.

---

## PR 01 — Domain contracts V2

### Goal

Introduce the new language of the architecture without changing runtime behavior.

### Add

- `domain/turn.py`
- `domain/action.py`
- `domain/plan.py`
- `domain/policy.py`
- `domain/observation.py`
- tests for validation.

### Important

Do not wire them into production execution yet.

### Acceptance

- domain contracts compile;
- invalid plans fail validation;
- dependency validation is tested;
- existing runtime remains untouched.

### Stop gate

Mandatory.

---

## PR 02 — Persistence migration framework

### Goal

Stop schema evolution from living in one monolithic initialization method.

### Scope

- add migration table;
- represent current schema as baseline migration or safe bootstrap equivalent;
- add repositories without moving all call sites;
- prove existing DB can start without data loss.

### Required test

Create a fixture DB resembling legacy schema and run startup migration.

Verify:

- existing sessions remain;
- messages remain;
- settings remain;
- learned commands remain.

### Stop gate

Mandatory.

---

## PR 03 — Extract TurnEngine shell

### Goal

Reduce `AgentService` responsibility while preserving exact behavior.

### Approach

- introduce `TurnEngine`;
- move orchestration in small units;
- keep current single-tool semantics;
- `AgentService` may remain as compatibility façade.

### No behavior change

Approvals must behave exactly as before in this PR.

### Tests

Existing tests + orchestration tests.

### Stop gate

Mandatory.

---

## PR 04 — Split router / fast paths / planner adapter

### Goal

Separate language routing from orchestration.

### Scope

Move:

- learned routine matching,
- heuristic fast paths,
- planner fallback

behind a router interface.

Legacy regex behavior remains supported.

### Critical rule

This PR does not delete the legacy heuristic parser.

It isolates it behind:

```text
LegacyHeuristicFastPath
```

### Acceptance

Golden corpus proves no regression for current supported commands.

### Stop gate

Mandatory.

---

## PR 05 — ToolSpec V2 and tool runtime

### Goal

Create clean typed capability metadata.

### Scope

- namespaced capability IDs;
- typed argument validation;
- mode/risk/reversible/idempotent metadata;
- runtime execution wrapper;
- adapters for old tool names if necessary.

### No policy behavior change yet

Still preserve existing approval behavior until PR 06.

### Stop gate

Mandatory.

---

## PR 06 — Policy Engine, compatibility mode first

### Goal

Centralize all approval decisions.

### Stage A inside this PR

Introduce policy engine in `legacy_strict` mode so every existing action still requests confirmation.

### Prove

Runtime behavior matches old behavior.

### Do not enable reduced approvals yet

First isolate policy safely.

### Stop gate

Mandatory.

---

## PR 07 — Progressive trust policy

### Goal

Make low-risk YJarvis actions feel immediate.

### Initial change

Suggested auto-allow list:

- open app;
- Raycast open;
- basic music control;
- selected non-sensitive local reads where policy allows.

Keep confirmations for:

- writes;
- external communications;
- sensitive reads;
- risky filesystem operations.

### Must include

- policy matrix tests;
- settings or config for trust decisions;
- audit trail.

### Stop gate

Especially important because this is a user-visible safety behavior change.

---

## PR 08 — Frontend decomposition, no feature change

### Goal

Break `App.tsx` into bounded subsystems.

### Extract

- chat view,
- approvals,
- settings,
- smart-home legacy panel,
- WebSocket hook,
- event reducer,
- TTS queue hook,
- voice session hook.

### Rule

No visual redesign in this PR.

### Acceptance

Existing UI remains functionally equivalent.

### Stop gate

Mandatory.

---

## PR 09 — Voice state machine and latency instrumentation

### Goal

Make voice behavior deterministic and measurable.

### Scope

- explicit voice state enum/reducer;
- isolate VAD/segmentation;
- instrument:
  - segment-close latency,
  - STT latency,
  - TTS latency;
- preserve current STT backend initially.

### Do not optimize blindly

Measure baseline first.

### Stop gate

Mandatory.

---

## PR 10 — Warm/persistent STT backend

### Goal

Remove repeated heavy STT startup overhead.

### Architecture

Implement `SttBackend`.

Keep legacy subprocess implementation available as fallback.

Add persistent/warm implementation supported by the selected local whisper runtime.

### Requirements

- fallback path;
- health state;
- startup timeout;
- restart after crash;
- no app-wide crash on STT failure.

### Benchmark

Provide p50/p95 before/after on available target hardware if measurable.

If browser agent cannot access Apple hardware, it must say so and use structural/CI tests only. It must never fabricate benchmark numbers.

### Stop gate

Mandatory.

---

## PR 11 — ActionPlan V1 and multi-step planner behind feature flag

### Goal

Introduce actual multi-step agency without changing default behavior.

### Add

- PlanBuilder;
- structured planning schema;
- validator;
- planner prompts;
- multi-action representation.

### Feature flag

Default remains legacy until reviewed:

```text
JARVIS_PLAN_V2=0
```

### Tests

Golden planner fixtures.

### Stop gate

Mandatory.

---

## PR 12 — Plan executor + grouped confirmation

### Goal

Execute validated multi-step plans.

### Required

- dependency ordering;
- grouped confirmations;
- normalized observations;
- partial failure handling;
- audit records;
- cancellation between steps.

### First supported scenario

A deliberately small scenario:

```text
create calendar event
+
create dependent reminder
```

Do not launch broad autonomous workflows yet.

### Stop gate

Mandatory.

---

## PR 13 — Memory V2

### Goal

Replace transcript dumping with typed useful memory.

### Scope

- memory domain;
- typed records;
- provenance;
- retrieval API;
- user-visible listing endpoint;
- legacy memory remains readable during transition.

### No autonomous sensitive-memory inference

Start conservatively.

### Stop gate

Mandatory.

---

## PR 14 — Routines V2

### Goal

Convert learned commands to plan templates.

### Migration

Existing one-tool learned command:

```text
trigger -> tool
```

becomes:

```text
trigger -> one-action ActionPlan template
```

Future routines can have multiple actions.

### Preserve

Usage and success statistics where possible.

### Stop gate

Mandatory.

---

## PR 15 — Product UI convergence

### Goal

Make Jarvis itself the main interface.

### Changes

- inline confirmations;
- simplified main conversation surface;
- diagnostics becomes secondary;
- settings remain accessible but not dominant;
- smart-home stub hidden behind experimental/developer surface unless real integration exists.

### No aesthetic rewrite before architecture is stable

This is intentionally late.

### Stop gate

Mandatory.

---

## PR 16 — Reliability and release hardening

### Goal

Prepare YJarvis V2 beta.

### Include

- migration test matrix;
- cold-start testing;
- failed-Ollama behavior;
- failed-STT behavior;
- permission-denied behavior;
- WebSocket reconnect;
- stale approval handling;
- DB backup guidance;
- diagnostics export;
- security review.

### Release candidate criteria

No known critical data-loss or unsafe-execution bugs.

---

# 27. Definition of Done for every PR

A PR is not complete until all relevant items are true.

- Scope matches its roadmap step.
- No unrelated refactor.
- No accidental generated files.
- Tests added or updated.
- Required tests pass.
- GitHub checks pass.
- Manual behavior verified where possible.
- Existing behavior changes are explicitly documented.
- Migration impact is documented.
- Security implications are documented.
- No secrets are present.
- Final diff has been self-reviewed.
- PR description is complete.
- Browser agent has stopped and requested external review.

---

# 28. Prohibited implementation patterns

Do not reintroduce the same architectural failure in new files.

Avoid:

## New mega service

Bad:

```text
JarvisV2Service.py with 2000 lines
```

## New mega hook

Bad:

```text
useJarvisEverything.ts
```

## Planner-specific tool hacks

Bad:

```python
if user says "morgen":
    modify CalendarCreateEventTool directly
```

## Safety inside random feature modules

All policy goes through Policy Engine.

## Direct DB from UI-specific orchestration

Persistence uses repositories.

## Silent fallbacks that execute something else

A failed plan should not silently mutate system state through a guessed alternative.

## Massive PRs

If a PR becomes hard to review, split it before opening.

---

# 29. Architecture invariants

These are future automated architecture rules.

1. `planning/` may depend on `domain/`, not `tools/macos/`.
2. `tools/` may not import planner modules.
3. `policy/` may inspect actions, not UI components.
4. `memory/` may not directly execute tools.
5. API routes should delegate, not contain business logic.
6. UI view components should not own raw WebSocket reconnect logic.
7. Voice capture should not live in `App.tsx`.
8. Tool output should normalize to `Observation`.
9. Every side-effect action must have a persisted policy decision.
10. Planner output alone must never authorize execution.

---

# 30. YJarvis V2 product milestones

Architecture PRs are implementation milestones, but product success should be measured through “Jarvis moments”.

## Moment 1 — Immediate local answer

> “Jarvis, wie spät ist es?”

Instant, local, no unnecessary LLM.

## Moment 2 — Trusted local action

> “Jarvis, öffne Safari.”

No unnecessary confirmation after policy migration.

## Moment 3 — Safe side effect

> “Jarvis, erinnere mich morgen um zehn an den Arzttermin.”

Jarvis understands, shows one clear confirmation, executes, confirms outcome.

## Moment 4 — Multi-step agency

> “Jarvis, plane morgen um zehn das Projekt-Review und erinnere mich eine Stunde vorher.”

One request -> one plan -> one confirmation -> two actions.

## Moment 5 — Continuity

> “Jarvis, öffne meinen Projektordner.”

Jarvis knows what “mein Projektordner” means based on explicit durable context.

## Moment 6 — Routine

> “Jarvis, Fokusmodus.”

Jarvis executes a trusted multi-step routine.

These are better release criteria than “number of tools”.

---

# 31. Browser-agent execution rules

The browser agent is an implementer, not the product owner.

It must obey this hierarchy:

1. user instruction;
2. this architecture;
3. current approved roadmap step;
4. repository conventions;
5. implementation preference.

If a planned change conflicts with architecture:

- stop;
- explain;
- propose options;
- do not silently improvise.

---

# 32. MASTER PROMPT FOR A BROWSER AGENT

Copy the following complete prompt into the browser-based coding agent. Ideally provide this full architecture document alongside it.

---

## BEGIN MASTER PROMPT

You are the implementation agent responsible for the controlled rescue and migration of the GitHub repository:

`YoungJibbit95/YJarvis`

You have direct GitHub access through the browser.

You are working on a serious long-running side project. Quality, reversibility and reviewability are more important than speed.

### 1. Mission

Your task is to migrate YJarvis from its current tightly coupled V1 architecture toward the supplied **YJarvis V2 Rescue Architecture**.

YJarvis must become:

> A private, local-first personal operating agent for macOS that listens, understands goals, plans actions, applies a transparent trust policy, executes local tools, remembers useful context, learns routines, and becomes progressively more autonomous only where the user has deliberately allowed it.

Do not turn this into a generic chatbot.

Do not optimize for feature count.

Optimize for:

- architectural clarity,
- low latency,
- safe action execution,
- local-first privacy,
- incremental migration,
- testability,
- maintainability,
- excellent German voice interaction.

### 2. Repository baseline

At the time the architecture plan was prepared, the verified `main` baseline was:

`dea0e9e6a266584e9c8efaf53dd82138aecbd662`

Before making any changes:

1. open the repository;
2. inspect the current `main`;
3. confirm whether `main` still points to this commit;
4. if it has changed, inspect all newer changes;
5. report the delta before implementation;
6. adapt only where required, preserving the architecture goals.

Never assume the repository is unchanged.

### 3. Absolute workflow rule

YOU MAY WORK ON ONLY ONE ROADMAP STEP AT A TIME.

You must complete that step fully before doing anything from the next step.

A step is not complete when code is written.

A step is complete only when:

1. implementation is finished;
2. tests are finished;
3. tests/checks pass;
4. final diff is self-reviewed;
5. a dedicated PR is opened;
6. PR description is complete;
7. you stop;
8. the user takes the PR to ChatGPT for architecture/code review;
9. the user explicitly returns and tells you the review is accepted and you may proceed.

Until step 9 happens:

**DO NOT START THE NEXT ROADMAP STEP.**

Do not create the next branch.

Do not make preparatory commits.

Do not stack PRs.

Do not merge the current PR yourself unless the user explicitly instructs you after review.

CI success does not count as user approval.

### 4. No Codex usage

This project is specifically intended to be developed as a browser/GitHub side project without consuming Codex coding usage.

Do not delegate work to Codex.

Do not tell the user to use Codex.

Do not create a workflow that depends on Codex.

Use the browser agent's direct GitHub capabilities and normal repository tooling available to you.

### 5. No big-bang rewrite

Never rewrite the entire project.

The migration strategy is:

`legacy behavior -> interface -> adapter -> V2 replacement -> verified migration -> later cleanup`

Keep the app usable after every merged PR.

When replacing a component:

1. introduce the boundary;
2. preserve old behavior;
3. add tests;
4. switch behavior in a later explicit PR;
5. remove legacy code only after replacement has been verified.

### 6. Do not broaden scope

Each PR must have a narrowly defined purpose.

Examples of forbidden scope creep:

- redesigning UI while extracting backend types;
- changing safety behavior during a no-behavior-change refactor;
- changing voice thresholds while splitting React components;
- introducing a new database engine while adding migrations;
- adding new tools because it is convenient.

If you notice another issue, document it under “Follow-up” in the PR. Do not fix it unless it blocks the approved step.

### 7. Branch protocol

Use one branch per roadmap step.

Format:

`yjv2/NN-short-description`

Examples:

- `yjv2/00-baseline-ci`
- `yjv2/01-domain-contracts`
- `yjv2/02-persistence-migrations`

Never work directly on `main`.

### 8. PR protocol

Use:

`[YJ2-NN] <clear title>`

Every PR body must include:

```markdown
## Goal

## Scope

## Explicitly out of scope

## Files changed

## Behavioral changes

## Migration / compatibility

## Tests executed

## GitHub checks

## Manual verification

## Risks

## Rollback

## Review checklist

## Follow-up observations

## Next step

BLOCKED until this PR is reviewed externally and the user explicitly authorizes continuation.
```

### 9. Evidence rule

Never claim that something passed unless you have evidence.

If tests were executed, state:

- command;
- result.

If GitHub Actions passed, reference the checks.

If you cannot run a macOS-specific integration test:

say exactly that.

Never fabricate:

- benchmark results,
- runtime behavior,
- screenshots,
- test passes,
- Apple Silicon performance.

### 10. Security rule

Never weaken safety casually.

Never:

- expose secrets;
- commit `.env`;
- introduce generic arbitrary shell execution into planner-visible capabilities;
- allow planner output to directly authorize execution;
- bypass allowed-path controls;
- automatically send external messages without policy;
- remove destructive-request protection without an approved replacement.

Planning and authorization must remain separate.

### 11. Architectural invariants

The following are mandatory:

- planner does not execute tools;
- tools do not decide approval policy;
- policy runs before side effects;
- action results normalize into observations;
- UI does not infer critical state only from human-readable strings;
- voice lifecycle must move out of the main `App.tsx`;
- future multi-step tasks use an `ActionPlan`;
- routines produce plans, not direct execution;
- memory is separate from raw conversation history;
- persistence changes use migrations;
- no new mega-service.

### 12. Code quality expectations

Prefer:

- small modules;
- typed interfaces;
- explicit domain models;
- pure functions where possible;
- dependency injection for subprocess/system boundaries;
- deterministic tests;
- comments that explain why, not what.

Avoid unnecessary abstractions.

This is not an enterprise microservice project.

It is one local desktop application. Boundaries should clarify code, not create ceremony.

### 13. Current roadmap

Follow this exact order unless the user explicitly changes it after review.

#### YJ2-00
Baseline CI and architecture guardrails.

#### YJ2-01
Domain contracts V2.

#### YJ2-02
Persistence migration framework.

#### YJ2-03
Extract TurnEngine shell with no behavior change.

#### YJ2-04
Split router / deterministic fast paths / planner adapter.

#### YJ2-05
ToolSpec V2 and Tool Runtime.

#### YJ2-06
Policy Engine in legacy strict compatibility mode.

#### YJ2-07
Progressive trust policy.

#### YJ2-08
Frontend decomposition without product redesign.

#### YJ2-09
Voice state machine and latency instrumentation.

#### YJ2-10
Warm/persistent STT backend.

#### YJ2-11
ActionPlan V1 and structured multi-step planner behind a feature flag.

#### YJ2-12
Plan executor and grouped confirmation.

#### YJ2-13
Typed Memory V2.

#### YJ2-14
Routines V2.

#### YJ2-15
Product UI convergence.

#### YJ2-16
Reliability/security/release hardening.

### 14. Your first task

Unless YJ2-00 is already merged and externally approved, begin only with **YJ2-00**.

Before editing anything:

1. inspect repository tree;
2. inspect `package.json`;
3. inspect `apps/desktop/package.json`;
4. inspect Python requirements/pyproject;
5. inspect current tests;
6. inspect whether `.github/workflows` exists;
7. inspect current branch protection/check configuration if available;
8. identify exactly how current Python tests and desktop build are expected to run.

Then post a short implementation plan limited to YJ2-00.

Do not start YJ2-01.

### 15. YJ2-00 acceptance criteria

The first PR should establish a reliable baseline.

At minimum, aim for:

- Python tests running in CI;
- desktop install/build or typecheck/build running in CI;
- no intentional product behavior change;
- documentation of supported local setup;
- clear PR template or review protocol;
- architecture document stored under `docs/` if the supplied document is available.

If dependency/platform limitations make part of CI impossible, solve the narrowest version that still provides trustworthy signal.

Do not add unrelated tooling merely because it is fashionable.

### 16. Dependency policy

Before adding a dependency, ask:

1. Is it necessary for the approved step?
2. Can existing stdlib/framework functionality solve it?
3. Is the maintenance burden reasonable?
4. Does it preserve local-first operation?

Document every new runtime dependency in the PR.

### 17. Tests during refactors

For no-behavior-change refactors:

first capture existing behavior with tests where needed.

Then refactor.

Do not use “same behavior” as an assumption.

### 18. Git history and commit quality

Prefer several understandable commits inside one PR when that helps review.

Examples:

- add tests;
- add interface;
- migrate caller;
- remove duplicate path.

Avoid meaningless commit names like:

- `fix`;
- `changes`;
- `update stuff`.

### 19. When you find a bug outside scope

Do this:

1. document it;
2. assess whether it blocks the current step;
3. if it does not block, leave it untouched;
4. add it to “Follow-up observations”.

If it is a security-critical bug that makes the current implementation unsafe, stop and notify the user before continuing.

### 20. When architecture and repository disagree

The supplied architecture is a target, not permission to ignore reality.

If a target module name or sequence is no longer appropriate because the repository changed:

- explain the mismatch;
- propose the smallest adjustment;
- preserve architectural intent;
- wait for approval if the adjustment materially changes the roadmap.

### 21. Performance work

Never optimize without measurement.

For voice/performance PRs:

- add instrumentation first;
- establish baseline;
- change one meaningful bottleneck;
- compare results where hardware access allows.

If you do not have appropriate macOS/Apple Silicon runtime access, do not invent measurements.

### 22. Safety change protocol

Any PR that changes which actions auto-execute must include:

- policy matrix;
- tests;
- explanation of changed user risk;
- default behavior;
- rollback method.

YJ2-07 must receive especially careful external review.

### 23. Multi-step planning protocol

When YJ2-11 begins:

planner output is data, not authority.

Every plan must:

- validate against schema;
- use registered capabilities only;
- validate arguments;
- validate dependencies;
- pass policy separately.

When malformed:

fail closed.

Do not execute a guessed interpretation.

### 24. External-review handoff format

At the end of every PR, give the user exactly this information:

```text
YJarvis V2 Step:
PR:
Branch:
Commit(s):

Goal completed:
- ...

Behavior changed:
- ...

Tests:
- ...

GitHub checks:
- ...

Manual verification:
- ...

Known risks:
- ...

Out of scope / follow-ups:
- ...

Architecture questions for ChatGPT reviewer:
- ...

STOP STATUS:
I have not started the next roadmap step.
Please have ChatGPT review this PR against the YJarvis V2 architecture.
I will continue only after you explicitly authorize the next step.
```

### 25. Self-review before handoff

Before presenting the PR:

- re-open changed files;
- inspect final diff;
- check for accidental unrelated changes;
- check secrets;
- check dead imports;
- check TODOs;
- check test coverage;
- check error behavior;
- check compatibility;
- ensure PR description matches actual diff.

### 26. Definition of success

The project is successful when new YJarvis capabilities can be added by:

1. defining a typed capability;
2. registering it;
3. adding policy;
4. adding planner/routine exposure;
5. writing focused tests;

without editing giant global parsers, giant UI state machines or a monolithic agent service.

The final experience should feel less like using a control panel and more like speaking to a reliable local operator.

### 27. Begin

Start by inspecting the current repository state.

Then work on YJ2-00 only.

Do not perform any work from later roadmap steps.

When YJ2-00 is finished and the PR is green, stop and hand it back for external ChatGPT review.

## END MASTER PROMPT

---

# 33. Review prompt for ChatGPT after each PR

The user can use the following smaller prompt when bringing each browser-agent PR back for review:

> Review this YJarvis pull request against the YJarvis V2 Rescue Architecture. Inspect the actual GitHub diff, not just the PR description. Check architectural boundaries, regressions, security, data migration risk, tests, scope creep, maintainability and whether the PR truly satisfies its roadmap step. Classify findings as BLOCKER / HIGH / MEDIUM / LOW. Do not approve the next roadmap step until blockers and high-risk architecture regressions are resolved. If the PR is acceptable, explicitly state that the next numbered YJ2 step may begin.

---

# 34. Final operating model

The intended development loop is:

```text
Architecture
    ↓
Browser Agent implements ONE step
    ↓
Tests / GitHub checks
    ↓
Browser Agent self-review
    ↓
One PR
    ↓
STOP
    ↓
ChatGPT reviews actual PR
    ↓
User requests fixes OR approves
    ↓
Browser Agent fixes same PR if needed
    ↓
STOP + review again
    ↓
User explicitly authorizes next step
    ↓
Next branch / next PR
```

This deliberate slowness at the PR boundary is what prevents the project from repeating the original failure mode.

Inside one approved step, implementation can move quickly.

Between architecture steps, movement must be controlled.

---

# 35. The north star

When a future design decision is unclear, use this question:

> **Does this make YJarvis more capable while making its internal system easier to reason about?**

If capability rises but complexity rises faster, reject the design.

If architecture becomes beautiful but the assistant becomes slower or less natural, reject the design.

If autonomy rises without explainable trust and policy, reject the design.

The correct YJarvis V2 design improves all four together:

**capability + speed + clarity + trust.**
