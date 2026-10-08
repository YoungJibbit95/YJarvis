# YJarvis UI vision — implemented in YJUX-V01

YJarvis is a personal assistant with a visible presence and a calm place for a
conversation. The interface gives the assistant, the conversation, decisions and
diagnostics different visual weight. It must make existing capabilities easier
to understand without implying capabilities or guarantees the backend lacks.

This is the canonical visual reference for the Product Experience track. It
replaces the earlier dashboard-like visual foundation, not the V2 architecture,
Windows addendum or accepted API contracts. The user's integrated YJUX-V01
directive authorizes this presentation milestone independently of the Core
roadmap. Subsequent Product steps still require external review and explicit
authorization. No future feature is implemented by this document.

## Visual identity and hierarchy

The environment uses deep navy (`#050a12`, `#091624`), cyan presence (`#68e4f2`),
cobalt work accents (`#769aff`), mint completion (`#9aebcd`), amber decisions
(`#f0c581`) and rose errors (`#ffadbb`). Main text is `#edf5fb`, secondary text
`#a0b2c6`. Color accompanies text; it never supplies the only status signal.
Static localized light, a faint grid and generous negative space create depth.
This is an original abstract visual language, without film characters or assets.

Typography uses installed system fonts: Segoe UI / system sans for controls and
reading, Bahnschrift / Avenir Next for the identity and major headings, Cascadia
Code / SF Mono / Consolas for literal technical data. There are no remote font
requests. Display size yields to usable controls in small windows.

1. **Presence:** a dedicated region with its own Orb and a textual state.
2. **Conversation:** the primary reading surface; assistant replies use a light
   leading rule, user messages a restrained surface. Empty space is intentional.
3. **Action:** a bounded composer and explicit approval controls.
4. **Information:** setup capabilities, model roles and system facts.
5. **Diagnostics:** connection details, event history, runtime values, exact
   identifiers and raw payloads are available through disclosures.

Do not turn all five levels into identical cards. The first-run hero, model rows,
hardware facts, conversation and approval documents have distinct compositions.
The small header core identifies the product; it is not a second status meter.

## Components and ownership

| Component / stylesheet | Responsibility |
| --- | --- |
| `design-system/tokens.css` | Shared color, font, spacing, control and motion constants |
| `app/AppShell.tsx`, `app/app-shell.css` | Identity, main navigation, command trigger and secondary runtime diagnostics |
| `app/PresenceStage.tsx`, `app/presence.css` | Pure presentation of assistant mode, microphone flag and latest dated agent event |
| `PresenceCore` | Decorative core, rings, aurora, grid, particles and symbolic speaking bars; reused in setup |
| `app/ActionReview.tsx` | Human action label, every supplied input, complete raw input and original decision callbacks |
| `app/AppFeedback.tsx` | Visible transport status and dismissible failure alerts, independent of diagnostics and assistant mode |
| `App.tsx`, `styles.css` | Existing state/handlers, conversation, composer, disclosures, settings groups and command dialog |
| `setup/SetupGate.tsx`, `setup/setup.css` | Activation composition using the existing setup gate |
| Existing model/hardware presenters | Role-first catalog and readable facts over unchanged validated DTOs |

The Orb occupies space beside the messages at a large desktop size. It is never
placed behind an opaque message plane. At widths up to 1000px or heights up to
800px it becomes a compact presence row above the conversation. Container-size
rules reduce decoration when expanded history or diagnostics need more room.
Messages and event history scroll independently; the composer does not shrink.
At especially narrow/short sizes the content region can scroll to retain access.

No presentation component starts a tool, probes a provider, installs a model or
infers hardware suitability. Existing App state remains the source of truth.

## Truthful state mapping

| Evidence already available | Presentation | Limits |
| --- | --- | --- |
| `AssistantMode = idle` | Quiet breathing core; “Im Ruhezustand” | Does not mean connected, healthy or configured |
| `AssistantMode = thinking` | Cobalt ring emphasis; “Anfrage aktiv” | Includes waiting for approval/execution; does not promise LLM inference |
| `AssistantMode = speaking` | Symbolic bars; “Sprachausgabe aktiv oder vorgemerkt” | Existing mode includes pending/queued TTS, not verified playback or amplitude |
| Existing microphone flag | Separate “Mikrofon aktiv/aus” text | Not inferred from Orb mode |
| `received` / `thinking` | “Anfrage empfangen” / “Anfrage wird verarbeitet” | Actual event, not a fabricated progress stage |
| `approval_required` / `executing` | “Freigabe benötigt” / “Aktion wird ausgeführt” | Text distinguishes both even when Orb mode remains thinking |
| `done` / `error` | “Vorgang abgeschlossen” / “Vorgang fehlgeschlagen” | Last event stays dated; completion is not persistent system readiness |
| Unknown event name | Neutral “Statusmeldung” | Exact value remains in event details |
| WebSocket connect/error/close/retry/open callbacks | Always visible connection line; interruption/retry in amber, cleared only by actual `onopen` | Transport connection is not backend health or model readiness |
| Chat, Voice, session and action failure callbacks | Visible, dismissible text alerts across all App tabs | Latest failure per category stays until dismissed/replaced; reconnect does not erase failures |
| Ordinary diagnostic/status string | “Verbindung & Hinweise” disclosure | Never parsed to derive severity or connection state |

The latest event is labelled **Letztes Agent-Ereignis**, with its timestamp. This
avoids representing a completed or failed historical event as the current state
of every run. The full bounded event list retains details, original state and
run ID. The mapping is display-only; no new backend state or transition exists.

Connection status uses a polite, atomic live region; failures use alerts. The
bounded failure list is keyboard-scrollable, long messages wrap, and closing a
failure returns focus to the stable feedback region. Diagnostics stay collapsed
by default without concealing interruptions, failed submissions or Voice errors.

## Existing product surfaces

**First run.** The large presence and activation copy lead to the real next
actions: repeat the check or enter the app when the backend is reachable. The
three component readouts preserve required/optional distinctions and all existing
reason texts. `checking`, `needs_setup`, `degraded`, `ready` and `error` remain
separate. There is no simulated installation, percentage, invented setup step or
claim that a present model file proves working inference/audio. Once App has
been entered, rechecks keep it mounted so drafts and session state survive.

**Models.** The roles are “Denken & Dialog”, “Dich verstehen” and “Mit dir
sprechen”. Names, descriptions, publisher, download size where supplied and
license uncertainty remain visible. Exact catalog/model/backend IDs, context,
publisher variants, source URLs and license provenance remain inspectable.
The catalog is informational: membership is not installation, recommendation or
platform availability. There are no download/install controls.

**Hardware.** OS, architecture, logical CPUs, RAM and storage scope remain exact
contract facts. Windows adapters distinguish hardware/software/unknown. A real
zero remains zero; unavailable data stays unknown. Shared system memory remains
an **upper bound**, never added VRAM. No inference speed, model ranking or GPU
capability is derived. Native DXGI behavior and all DTO parsers are unchanged.

**Approvals.** Known legacy tool names get a readable action name. Every supplied
input, including unfamiliar keys and nested values, is visible before the raw
JSON disclosure. Unknown tools use “Aktion prüfen” and the exact tool name.
Tool/run/approval IDs and full input JSON remain inspectable. Freigeben/Ablehnen
pass the original approval ID and exact `approve`/`deny` decision. No risk grade,
reversibility, safety promise or execution outcome is invented. Only pending
requests are described as requiring a decision; the UI does not claim every
possible legacy action requires approval.

**Settings.** Actual controls are grouped as Allgemein, Modelle, Stimme and
Dateizugriff. Advanced model connection/files and voice backend/file controls are
local disclosures within their groups. Allowed paths remain their own visible
section. Existing drafts, normalization, save request and post-save recheck are
unchanged. No autosave, new persistence, migration or empty future section exists.

**Commands.** A native modal dialog gives the focused command surface its own
layer and makes background content inert. Opening focuses search; closing returns
focus to the connected invoking element. Escape, Ctrl/Meta+K, filtering, disabled
conditions and dispatch are retained. German labels retain previous English
search aliases. The Smart Home view still explicitly identifies its template.

## Motion and accessibility

Motion is CSS decoration. Breathing uses 8 seconds (thinking: 5), rings use
18/24/28 seconds (thinking: 12), state opacity transitions 360ms, feedback 160ms,
surface entry 300ms and one-shot completion 450ms. Speaking bars use a restrained
1.8-second symbolic rhythm. No amplitude measurement is implied. Animations
change transform/opacity; atmospheric layers and glows stay static. No new JS
animation loop, WebGL, large animated blur or runtime dependency is introduced.
The existing microphone/audio loop is untouched.

`prefers-reduced-motion: reduce` disables all animations, transitions and smooth
scrolling through the shared primitive rules. Core, rings and text remain a
complete static composition; the presence is not removed. Forced-colors rules
retain visible core/ring borders, selected navigation, controls and content
boundaries while hiding decorative atmospheric layers. Native details/buttons,
explicit search/composer labels, navigation current-page semantics, the skip
link and strong focus outlines are retained. Decoration is aria-hidden and does
not intercept pointer events. Important meaning has a text counterpart.

## Examples and review criteria

- Empty chat: presence at left, invitation in the reading area, bounded composer
  below; setup availability controls the existing disabled state.
- Running request awaiting approval: thinking presence plus a dated amber
  “Freigabe benötigt”; no assertion that the microphone is listening.
- Completed text with queued TTS: speaking label explicitly allows queued output,
  while the separate last event may already say completed.
- Unknown adapter memory: “Unbekannt”; a software adapter with zero dedicated
  memory still shows “0 GiB”.
- Unknown action with nested inputs: neutral heading, all values and literal
  payload, followed by the same two explicit decisions.

Review actual rendered UI at 1320×860, 960×760, 480×780 and 1200×650, including
empty/long/streaming chat, setup failures, pending approvals, unknown metadata,
settings editing, keyboard focus and motion reduction. Mark synthetic run/audio
fixtures visibly and keep them outside production. Browser rendering, native
Electron, macOS audio and measured frame rate are separate evidence claims.

Reject visual drift when the Orb disappears behind content, every surface becomes
an equivalent card, diagnostics displace conversation, a glow reduces legibility,
decoration hides decisions/composer, unknown data becomes a number, a status
overstates its evidence, or motion becomes necessary to understand the state.
Reject behavior drift when a visual extraction changes a handler, request,
approval decision, draft lifetime, reconnect path, audio queue or DTO meaning.

The recovery is reversible by reverting the single YJUX-V01 implementation PR.
It introduces no data migration and requires no deletion of local runtime data.
