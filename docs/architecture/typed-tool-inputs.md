# YJ2-05B1: typed capability inputs, still inert

Historical 05B1 note: [YJ2-05B2](typed-tool-outputs.md) populates output references.
The accepted input contracts and the inert runtime boundary remain unchanged.

Initial main: `35a04e43598611e6cfc5c67ccafa05ae9915ad74`, the accepted PR #11
squash merge. Post-merge run `37688306762` passed all six checks before this branch.
Final base main: `1c9a338137c6211f88f88239d82cfb189d47ef7d`, after the concurrent
PR #12 UI foundations merge. Its post-merge run `37689172860` also passed 6/6;
the branch was fast-forwarded before final validation. No UI changes belong to 05B1.
The delta from architecture baseline `dea0e9e6a266584e9c8efaf53dd82138aecbd662`
contains the accepted YJ2-00 through 05A, YJW-00A/B/B.1 and separate YJUX-00A steps.

`domain/tool_inputs.py` defines 18 Pydantic input classes. Every catalog entry
references its class; **all output_model references remain None** (unmodeled).
The empty `ClipboardReadInput` is a real model with no fields. Catalog identity,
descriptions, risks, modes, flags and timeout metadata are unchanged.

## Contract inventory

All fields forbid extras and use strict scalar types: no numeric strings, bytes
as text, integers as booleans, or booleans/floats as integers. Models inherit
freezing, default validation and instance revalidation from `DomainModel`.
Optional `?` fields below accept None and default to None. Other defaults are
explicit; a listed default means the field can be omitted. Text is preserved
without trimming, truncation or newline replacement. `nonblank` means at least
one non-whitespace character. Length limits count characters, not bytes.

| Capability / model | Required fields | Optional fields / defaults / bounds |
| --- | --- | --- |
| url.open / UrlOpenInput | url: strict AnyHttpUrl | HTTP(S), host required; Pydantic URL parsing/normalization |
| apps.open / AppOpenInput | app_name: display name | 1..200 characters; grammar below |
| raycast.open / RaycastOpenInput | none | fallback_text?: text |
| raycast.command.run / RaycastCommandRunInput | owner, extension, command: segments | fallback_text?: text; background: bool = true |
| clipboard.read / ClipboardReadInput | none | no fields |
| clipboard.write / ClipboardWriteInput | text: text, empty allowed | none |
| reminders.create / ReminderCreateInput | title: nonblank | notes?: text; due_at?: datetime |
| reminders.list / ReminderListInput | none | list_name?: nonblank, max 120; limit: int = 8, 1..30 |
| calendar.events.create / CalendarCreateEventInput | title: nonblank | start_at?: datetime; start_offset_minutes: int = 5; duration_minutes: int = 60, 1..1440 |
| calendar.events.list / CalendarListEventsInput | none | days_ahead: int = 7, 1..90; limit: int = 10, 1..40 |
| notes.create / NotesCreateInput | title: nonblank, max 180; content: text, max 8000 | folder?: nonblank, max 120 |
| notes.search / NotesSearchInput | none | query: text = empty, max 200; folder?: nonblank, max 120; limit: int = 8, 1..30 |
| mail.drafts.create / MailCreateDraftInput | subject: nonblank, max 220; content: text, max 12000 | recipient?: nonblank, max 220 |
| messages.send / MessagesSendInput | recipient: nonblank, max 220; text: nonblank, max 4000 | none |
| contacts.search / ContactsSearchInput | none | query: text = empty, max 180; limit: int = 6, 1..30 |
| music.control / MusicControlInput | action: play, pause, next or previous | none |
| files.read / FileReadInput | path: nonblank text | none |
| files.write / FileWriteInput | path: nonblank text; content: text, empty allowed | mode: overwrite or append = overwrite |

Raycast segments have 1..121 ASCII letters/digits/dots/underscores/hyphens and
start with a letter/digit. This is integration identity, not a generic launcher.
App display names begin with a Unicode letter/digit, followed by letters/digits,
underscore, spaces, dots, parentheses, plus or hyphen. Leading/trailing whitespace,
paths, shell punctuation, command flags, reverse-DNS-like identifiers with three
or more segments, and .app/.exe/.com/.bat/.cmd/.ps1/.scpt suffixes are rejected.
This intentionally narrow grammar can reject unusual legitimate display names;
it is not an installed-app lookup, shell escaping or an execution safety boundary.
No provider may interpret a name as a command. Provider resolution is future work.

Datetimes accept datetime objects or ISO datetime strings containing a time.
Date-only values, numeric epochs and relative prose are rejected. Naive values
remain naive; explicit offsets remain unchanged. No host timezone, clock lookup,
conversion or future-date constraint is introduced. As in legacy, an explicit
start_at takes precedence over the relative offset, whose default remains +5
minutes. Both fields may be present; negative offsets remain representable.
Validation computes no start time. A future adapter/provider must explicitly
resolve naive timezone semantics before execution; this PR does not decide them.

## Deliberate differences from legacy

Limits reject instead of clamp; bounded text rejects instead of truncates.
Required title/subject/content/text fields are not synthesized from legacy
fallbacks. Clipboard/file content may intentionally be empty. Empty search query
means an unfiltered search; an omitted folder/list means no explicit selection.
Optional selectors use None rather than legacy empty-string sentinels.
Optional free text also accepts explicit empty strings. Music/file enum values
must match exactly; there is no case folding. Recipient replaces legacy `to` for
messages and mail, without an alias or address/service/provider validation.
HTTP(S) URL parsing may normalize the URL; it performs no network request and
does not implement URL access policy. App names are semantic display names.
File paths remain opaque strings, including relative, drive and UNC forms:
**these models are not path safety**, availability, authorization or OS policy.

## Inert boundary, evidence and rollback

No production runtime imports these models. Existing ToolCallIntent dictionaries,
legacy input_schema, planner specs, approvals, learned commands, wire/DB names
and ToolRegistry.execute remain unchanged. There is no legacy-to-V2 adapter,
output contract, ToolRuntime, policy or provider dependency. Domain owns V2
contracts; the legacy mapping remains compatibility knowledge and must never
pull legacy providers into domain. The descriptive 30-second timeout must be
reviewed before future enforcement; this PR does not enforce it.

Tests cover the complete mapping, exact classes, required/default/optional fields,
invalid types/extras/bounds/enums, datetime and name boundaries, and JSON round trips.
The isolated process imports and validates all 18 examples under the existing
file-write/process/network/DB audit guard, with no event/provider imports. AST
gates prohibit runtime wiring. Real legacy clipboard dispatch still accepts
coerced, missing and extra input values that V2 rejects (native command mocked).
Unchanged planner/lifecycle tests cover legacy specs and all 18 approval identities.
Full-suite and CI evidence belongs in the PR; native macOS integration is not claimed.

Rollback: revert this PR. There is no data/configuration migration. Outputs (05B2),
adapters, ToolRuntime (05C) and YJW-01 are separate, blocked review gates.
