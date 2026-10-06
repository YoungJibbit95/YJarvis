# YJ2-01: isolated V2 domain contracts

## Scope and provenance

This is an implementation guide for **YJ2-01**, not a replacement or silent
revision of the supplied [V2 architecture](YJarvis_V2_Architecture_and_Browser_Agent_Master_Prompt.md).
It implements the vocabulary in architecture sections 5.1–5.5 and roadmap PR 01.
The original architecture file is unchanged.

YJ2-00 was externally accepted by the user and squash-merged as
`76180f594319a076a6d8e8be74ee4584c6e9d029`. All four checks in main's Baseline CI
run `37500359870` passed before this branch was created from that exact commit.
The only change from the architecture's original `dea0e9e...` baseline is the
accepted YJ2-00 infrastructure/documentation and its two type-only annotations.

**Nothing here is wired into the existing application.** `AgentService`, APIs,
legacy `schemas.py`, tool routing, approvals, database, voice, desktop, memory
and routines remain unchanged. There is no TurnEngine, planner, policy engine,
executor, migration, feature flag, or later-step scaffold in this change.

## Why Pydantic models, not dataclasses

The backend already pins **Pydantic 2.9.2** in both runtime dependency manifests
and uses `BaseModel` for its existing schemas. Reusing that dependency provides
constructor validation, nested model validation, JSON round trips, structured
validation errors and JSON Schema without adding a second serialization layer.
Plain dataclasses would require hand-built parsing/validation for these contracts.
No runtime or development dependency is added or upgraded.

Implementation follows the existing pinned API, not a new Pydantic release.
See the [Pydantic 2.9 model documentation](https://docs.pydantic.dev/2.9/concepts/models/)
and [configuration reference](https://docs.pydantic.dev/2.9/api/config/).

## Module boundaries

| Module under `jarvis_agent/domain/` | Responsibility |
| --- | --- |
| `common.py` | Shared model configuration, UUID/text/time/JSON primitives |
| `turn.py` | `Turn`, `InputMode`, `TurnState`; timestamp ordering |
| `action.py` | `Action`, `ActionMode`, `RiskLevel`; capability syntax |
| `plan.py` | `PlannedAction`, `ActionPlan`, `FailureStrategy`, `PlanStatus`; dependency validation |
| `policy.py` | `PolicyDecision`, `PolicyVerdict`; decision record only |
| `observation.py` | `Observation`; result consistency |
| `__init__.py` | Explicit public contract exports only |

The package imports only the standard library, Pydantic and its own modules.
It does not import application configuration, tools, databases, HTTP clients,
LLMs or any legacy service. Existing production modules do not import it.

## Concrete validation decisions

These are the implementation choices where the architecture gives pseudocode
rather than a complete parsing specification. They do not add product behavior.

**IDs.** Every `id`, `session_id`, `turn_id`, `action_id` and dependency reference
uses a non-nil `uuid.UUID`. UUID instances and UUID strings are accepted; arbitrary
labels, numbers, byte strings and the nil UUID are rejected. No UUID version is
imposed. The architecture's illustrative `a1`/`a2` labels are not wire IDs for
these typed contracts. Callers supply IDs; validation never generates them.

**Enums.** Wire values match section 5 exactly: input `text|voice`; the ten Turn
states; action modes `read|write|external_side_effect|system`; risk
`low|medium|high|critical`; the eight plan statuses; failure strategy
`stop|continue|ask_user`; verdict `allow|confirm|deny`. The enums are Python
`StrEnum` classes. There are no implicit mappings from legacy state labels.

**Required data and defaults.** All architecture fields are required except the
safe structural defaults: Turn state `received`, plan status `draft`, empty
`depends_on`, failure strategy `stop`, and nullable observation error fields.
Arguments and observation data must be explicitly supplied, even when `{}`.
Risk, mode, reversibility and result requirements are never inferred.

**Text and capability names.** Text fields must be strings containing at least
one non-whitespace character. Text is not trimmed or rewritten. Capability names
are lowercase dotted identifiers, with letters/digits/underscores inside each
segment, for example `calendar.create_event`. This checks naming syntax only:
it does not assert registration or look up a capability schema.

**Timestamps.** Callers supply timezone-aware `datetime` objects or ISO 8601
strings. Naive timestamps, date-only values and numeric epochs are rejected.
Supplied timezone offsets are retained. A Turn's `updated_at` must not precede
`created_at`; comparison uses UTC instants, including ambiguous DST folds.
There are no clock reads or automatic lifecycle timestamps.

**JSON data.** `Action.arguments` and `Observation.data` contain JSON objects
with string keys and recursively only objects, arrays, strings, finite numbers,
booleans and null. Tuples/sets, bytes, arbitrary objects, callables, non-string
keys, NaN/Infinity and cycles are rejected rather than coerced. Strings that look
like commands remain strings. Validation does not execute or interpret them.

**Booleans and duration.** Boolean fields use `StrictBool`. Values such as `1`
and `"true"` are rejected. `duration_ms` is a nonnegative strict integer; booleans,
floats and numeric strings are not accepted as durations.

**Observations.** A successful observation cannot include error fields. A failed
observation requires a nonblank `error_code`; `error_detail` is optional. Error
codes remain open strings: no future tool/error taxonomy is invented here.

**Extra fields.** Unknown fields are rejected at every model level, including
nested actions and planned actions. This prevents silent loss of misspelled or
unrecognized contract fields.

## Plan dependencies: validation, not execution

A Turn may need no actions and therefore no ActionPlan. A materialized ActionPlan
requires at least one PlannedAction. Each dependency refers to another
`PlannedAction.action.id` in that same plan; PlannedAction has no separate ID.

Validation rejects duplicate action IDs, duplicate dependencies, self-references,
missing/cross-plan references and cycles, including cycles in disconnected
components. Independent actions, diamond DAGs and forward references are valid.
A deterministic, iterative Kahn traversal checks acyclicity in O(V + E); it does
not run actions, produce an execution schedule, reorder the supplied plan, or
inspect external state. Long-chain tests do not depend on Python recursion depth.

The architecture's arrays are accepted as lists and serialize as JSON arrays.
In Python, `actions` and `depends_on` are stored as tuples so their structure cannot
be edited in place after validation. This is an in-memory representation choice,
not a wire-format or roadmap change.

Status/verdict values are **records, not evidence or authority**. Constructing an
`approved` plan, an `allow` PolicyDecision or a successful Observation neither
proves that an action occurred nor authorizes one. No state-transition graph,
capability registration check, argument schema lookup, policy evaluation,
persistence or cross-entity lookup exists in YJ2-01. Those belong to their later,
explicitly authorized implementation steps.

## Construction, serialization and mutation boundaries

Use constructors, `model_validate(...)` or `model_validate_json(...)`. Export with
`model_dump(mode="json")` / `model_dump_json()`. All contracts expose
`model_json_schema()`. JSON Schema describes field shapes, not cross-field rules
such as DAG acyclicity or observation consistency: consumers must run model
validation, not treat schema validation alone as sufficient.

Models disable attribute reassignment and use `revalidate_instances="always"`.
Already-created nested models are revalidated rather than automatically trusted.
Inputs are copied during typed validation; editing an input dictionary/list does
not silently change the constructed contract.

**These are not deeply immutable or tamper-proof authorization objects.** JSON
payload dictionaries/lists remain mutable. Revalidate after modifying payloads
or crossing a boundary. Pydantic's `model_construct()` and
`model_copy(update=...)` deliberately bypass validation; do not use them for
untrusted construction or validated updates. Construct a new validated record
instead. Tests verify that later normal validation catches invalid copied or
nested model instances. No custom replacement for Pydantic's model framework is
introduced.

For example, this constructs inert data only:

```python
from uuid import UUID

from jarvis_agent.domain import Action, ActionPlan, PlannedAction

action = Action(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    capability="apps.open",
    arguments={"app_name": "Safari"},
    mode="system",
    risk="low",
    reversible=True,
    requires_result=True,
)
plan = ActionPlan(
    id=UUID("00000000-0000-0000-0000-000000000020"),
    turn_id=UUID("00000000-0000-0000-0000-000000000010"),
    goal="Open Safari",
    summary="One illustrative action; no execution",
    actions=[PlannedAction(action=action)],
)
assert ActionPlan.model_validate_json(plan.model_dump_json()) == plan
```

The illustrative metadata is not a registry entry or an enabled policy rule.

## Tests and review

From the supported development environment described in `docs/development.md`:

```bash
python -m pytest tests/domain -q
python -m pytest -q
python -m ruff check apps/agent/jarvis_agent tests
npm run typecheck
npm run build
```

Focused tests cover positive/negative contract examples, every enum value, missing
and extra fields, UUID/time/JSON boundaries, graph failures and valid DAGs,
serialization/schema availability, mutation/revalidation and runtime isolation.
An isolated subprocess audits against subprocess execution, socket use, SQLite
connections and file writes during contract import/validation. A static import
gate also verifies that legacy production modules do not import the contracts.
That YJ2-01-specific no-wiring gate must only be revised in explicitly authorized
future integration work; it is not a claim that domain imports are forbidden
forever. No CI filters, test skips, weaker lint options or new CI dependencies are
needed. Full-suite and desktop checks remain the existing four CI jobs.

Known baseline risks remain unchanged: YJ2-00 reported 21 npm vulnerabilities
(2 critical, 11 high, 7 moderate, 1 low); main has no server-side branch protection;
interactive macOS/Apple Silicon smoke tests are unavailable here. Python transitive
dependencies are not fully locked. This PR does not fix or provide security/runtime
clearance for those risks. Exact executed environments, results and CI links belong
in the PR evidence, not an invented macOS result.

After the final checks and self-review, stop for external ChatGPT review. Do not
merge YJ2-01, start YJ2-02, or create persistence/migration scaffolding.
