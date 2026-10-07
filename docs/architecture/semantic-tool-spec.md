# YJ2-05A: descriptive ToolSpec V2 and capability catalog

Historical 05A note: [YJ2-05B1](typed-tool-inputs.md) now populates the 18 input
references. Outputs remain unmodeled; none of these contracts is wired to runtime.

Base main: `bc18eb2fd11cc753e110acdf3d9a4472edf3950c`, after the externally
accepted YJW-00B.1 squash merge. Post-merge run `37685689305` passed all six checks,
including 527 Python and 22 startup tests on both Linux and Windows.

## Boundary and representation

`domain/tool_spec.py` defines a frozen Pydantic `ToolSpecV2` using the accepted
`CapabilityName`, `ActionMode` and `RiskLevel` types. All ten fields are explicit:
capability, description, input_model, output_model, mode, default_risk, reversible,
idempotent, supports_dry_run and timeout_seconds. Text must be nonblank, flags
must be booleans, timeouts must be positive finite numbers, and extra fields are
rejected. Specs have no execute, authorization, approval, provider or availability
field/method. Pydantic's unvalidated construction/copy APIs are not validation
boundaries; `model_validate` revalidates instances.

Input/output references accept Pydantic model **classes**, not free dictionaries,
instances, callbacks or import-path strings. Spec validation neither instantiates
these classes nor invokes their payload validators. These are Python code metadata,
not JSON/wire/DB DTOs. The class definitions themselves remain ordinary Python
classes; freezing a spec does not freeze a referenced class definition.

To keep this PR small, all 18 catalog entries explicitly use `None` for input_model
and output_model: **not modeled yet**, not an empty schema or permission to accept
arbitrary input. Typed population/legacy adapters belong to a separately approved
05B; there is no adapter or typed argument enforcement in 05A. The complete
descriptive inventory is usable for static inspection without implying execution
readiness. Legacy input validation remains exactly where it is today.

`domain/capability_catalog.py` exposes the read-only `LEGACY_TOOL_CATALOG` mapping
from exact legacy names to frozen specs. It lives beside the contracts to preserve
the existing domain isolation gate. It imports no `tools` package (whose current
initializer eagerly imports the registry/providers). Indexing an unknown name
raises `KeyError`; there is no alias guessing, name conversion or runtime lookup.

## Naming and complete compatibility matrix

Capability IDs use lowercase, dotted semantic segments, with the same syntax as
`Action.capability`. Nested nouns are explicit, e.g. `calendar.events.create` and
`mail.drafts.create`. Provider/OS/implementation names do not appear in generic IDs.
All 18 mappings are one-to-one; no duplicate capability aliases are intended.

| Legacy tool name | Capability | Mode | Default risk | Idempotent |
| --- | --- | --- | --- | --- |
| open_url | url.open | external_side_effect | medium | false |
| open_app | apps.open | system | medium | false |
| raycast_open | raycast.open | system | low | false |
| raycast_run_command | raycast.command.run | external_side_effect | high | false |
| clipboard_read | clipboard.read | read | low | true |
| clipboard_write | clipboard.write | write | medium | false |
| reminder_create | reminders.create | write | medium | false |
| reminder_list | reminders.list | read | low | true |
| calendar_create_event | calendar.events.create | write | medium | false |
| calendar_list_events | calendar.events.list | read | low | true |
| notes_create | notes.create | write | medium | false |
| notes_search | notes.search | read | low | true |
| mail_create_draft | mail.drafts.create | write | medium | false |
| messages_send | messages.send | external_side_effect | high | false |
| contacts_search | contacts.search | read | low | true |
| music_control | music.control | system | low | false |
| file_read | files.read | read | medium | true |
| file_write | files.write | write | high | false |

Raycast is intentionally named as a specific optional integration, currently
macOS-related. It is not represented as a universal launcher. A later provider
resolver must advertise it only when a provider is actually available.

## Classification decisions

- URL opening may contact external services; Raycast extension commands can have
  opaque external effects. Both use `external_side_effect`, conservatively. The
  Raycast command's V2 default risk is high; its **legacy** medium risk is unchanged.
- Other risk labels retain existing defaults. Low/read never means automatic
  approval, non-sensitive data, or safe availability on the current machine.
- App opening and music playback change application/system state. Music includes
  next/previous; file writing includes append. Neither is promised idempotent.
- Create/write operations can create folders, duplicate records or affect synced
  application data. Draft creation does not send mail; messages do send externally.
- Only read operations claim idempotence (no intended data mutation, not identical
  output across time). All other operations conservatively make no such guarantee.
- `reversible=False` and `supports_dry_run=False` for every entry: no rollback or
  dry-run implementation is promised. This does not say a user can never undo an
  action manually.
- Every entry has a **descriptive V2 budget of 30 seconds**, not a measured latency
  or an existing enforced legacy timeout. A future runtime must explicitly review
  and implement enforcement. No timeout is applied by this PR.

## Known is not available, and description is not authority

Catalog membership says a capability is known. It says nothing about installed
applications, permissions, host OS or provider availability. There is no hardcoded
`available=True`, discovery, provider resolution, platform probing or planner
advertising. Later resolution must distinguish known from available explicitly.

The existing path remains `ToolCallIntent` -> legacy tool name -> existing approval
-> `ToolRegistry.execute()`. All 18 legacy tools remain approval-required. Planner
input schemas, ranking, learned commands, routing, wire names and stored DB names
are unchanged. No production runtime module imports the new domain/catalog code.
No new policy, ToolRuntime, ActionPlan wiring, DB schema or dependency is introduced.

## Evidence and rollback

Contract/catalog tests cover validation, freezing, typed references without payload
execution, complete registry coverage, uniqueness, explicit unknown-name failures,
legacy execution dispatch, all 18 learned-command approval events and persisted
legacy names. Existing lifecycle/routing/planner tests remain unchanged. The domain
AST import gates and fresh-process audit guard now also cover catalog import and
spec validation, rejecting process/network/DB/file-write side effects.

Exact suite/CI results are recorded in the PR. Windows/Linux tests do not claim
macOS native integration, Windows provider parity or any newly available tool.
Rollback is a revert of this PR: no data migration or runtime configuration changes.
05B typed population and 05C ToolRuntime are separate future review gates, not work
started here. Leave this PR unmerged for external review; YJW-01 is also blocked.
