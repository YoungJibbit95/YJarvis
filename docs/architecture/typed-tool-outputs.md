# YJ2-05B2: successful capability data, still inert

Base main: `a79cc256ae0d4bc2df4f0a631812f5a1f7d83b97`, the externally accepted
PR #13 squash merge. After the concurrent UI PR #14 merge, PR #13 was synchronized
with main `65a3d974adb4f8e2e9ba72fe5d47a5b9b44b95ab`; its reviewed patch remained
unchanged. Synchronization CI and post-merge main CI `37698339510` passed all six
checks before 05B2 began. The delta from architecture baseline
`dea0e9e6a266584e9c8efaf53dd82138aecbd662` contains accepted YJ2-00 through 05B1,
YJW-00A/B/B.1 and the separate YJUX-00A/B UI work.

## Complete output matrix

Every spec now references both an input and an output class. All input classes,
capability IDs, legacy mappings and other spec metadata are unchanged.
`domain/tool_outputs.py` contains seven frozen, extra-forbid models for 18 specs.
There are no untyped dictionaries or new dependencies.

| Capability | Output model | Successful data |
| --- | --- | --- |
| url.open | NoDataOutput | empty |
| apps.open | NoDataOutput | empty |
| raycast.open | NoDataOutput | empty |
| raycast.command.run | NoDataOutput | empty |
| clipboard.read | ClipboardReadOutput | text: strict string |
| clipboard.write | NoDataOutput | empty |
| reminders.create | NoDataOutput | empty |
| reminders.list | ReminderListOutput | titles: ordered strict strings |
| calendar.events.create | NoDataOutput | empty |
| calendar.events.list | CalendarListEventsOutput | titles: ordered strict strings |
| notes.create | NoDataOutput | empty |
| notes.search | NotesSearchOutput | titles: ordered strict strings |
| mail.drafts.create | NoDataOutput | empty |
| messages.send | NoDataOutput | empty |
| contacts.search | ContactsSearchOutput | names: ordered strict strings |
| music.control | NoDataOutput | empty |
| files.read | FileReadOutput | content: strict string |
| files.write | NoDataOutput | empty |

All data fields are required, with no implicit empty/default result and no None.
An explicit empty string or empty collection is valid data. Ordered collections
accept Python lists/tuples and JSON arrays, stored as immutable tuples. Sets,
iterators, strings-as-arrays, non-string elements and entity dictionaries are
rejected. Strings are preserved exactly, including blanks, newlines and Unicode.
Collections preserve duplicates and producer order; no sorting, deduplication,
trimming, parsing, coercion or truncation is performed.

## Why these outputs are deliberately small

The twelve side-effect capabilities have no stable returned semantic data in the
current interfaces. Their shared NoDataOutput is an actual empty model, not None,
an implicit success flag or a promise of a generated object ID. Raycast only
launches the integration/command; arbitrary extension result data is not promised.
Creating an empty model does not prove any side effect ran or was authorized.

Clipboard text is stable data. File content means the **full decoded text**, with
no synthetic preview marker. There is no V2 6000-character cap or `truncated`
field. Legacy FileReadTool currently returns a capped display string; that string
cannot simply be relabeled as this full-content contract. A future provider must
supply full text or report failure / obtain a separately reviewed richer contract.
Validation cannot verify completeness and does not read files or choose an
encoding/error policy. Literal marker-like text in a file remains ordinary data.

List/search results expose only returned reminder/event/note titles or contact
display names, which the existing sources already know independently of rendering.
They describe the returned selection within the request's filters/limit, not an
exhaustive inventory or stable identity. Empty/duplicate/blank labels are preserved;
names cannot safely identify entities for later actions. Event start and reminder
due times, IDs, addresses, bodies, pagination/completeness flags, provider metadata
and timezone interpretation are deliberately not modeled. This is a limited result
contract, not a rich entity schema or a protocol for follow-up actions.

No existing prose is parsed. Delimiters, translated headings and locale-formatted
dates in today's ToolResult.output are presentation, not a future domain protocol.
The future provider must supply semantic data directly; a later compatibility step
must not invent IDs or reconstruct unavailable fields from display strings.

## Output is not Observation

The future boundary is `Provider / ToolRuntime -> typed capability output ->
Observation`. Output holds successful domain data. Observation holds action linkage,
success/failure, summary, error codes/details, duration and occurred_at. Policy and
approval retain their own responsibilities. Outputs contain none of those fields,
no generic `message`/`output` string and no authority to execute. Failure must not
be represented by silently replacing missing data with an empty successful result.
No conversion into Observation is implemented or implied by model validation.

The current path remains `ToolCallIntent -> legacy tool_name -> approval ->
ToolRegistry.execute() -> legacy ToolResult`. No production runtime module imports
the new models. There is no input/output adapter, normalizer, ToolRuntime, timeout
enforcement, cancellation runtime, dry run, provider resolution or policy work.
Input grammar, naive datetimes, offsets, recipient naming and path safety remain
unchanged review boundaries. The descriptive 30-second timeout remains unenforced.

## Evidence and rollback

Fixtures capture the 05B1 catalog metadata/input class identities and all 18 legacy
planner schemas from the inspected base. Tests require exact equality except the
new output reference. Existing input and planner tests remain unchanged. Output
tests cover every reference, strict required fields, freezing, unknown fields,
round trips, noncoercion and rejected execution/Observation metadata. The existing
fresh-process audit guard now validates all 18 outputs as well as inputs, with its
process/network/DB/file-write negative controls unchanged. AST gates continue to
reject non-domain imports and production runtime wiring. Registry regression tests
return the original legacy success/failure ToolResult object without conversion.

Revert this PR to roll back. No stored data or configuration migration is needed.
Adapters, ToolRuntime and YJW-01 remain blocked until separate review and approval.
