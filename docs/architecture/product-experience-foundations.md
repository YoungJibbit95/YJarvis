# YJUX-00A — Design tokens and native UI primitives

## Authorization and baseline

The user's Product Experience execution instructions of 2026-10-07 authorize
one small YJUX-00 implementation cycle alongside the separate Core track.
For this cycle they supersede the older UI exclusion in the root contribution
instructions. They do not authorize another Core step or the complete UX roadmap.
The architecture remains a migration target, not a description of current features.

Inspected base: `bc18eb2fd11cc753e110acdf3d9a4472edf3950c` (`main`). Since the
original `dea0e9e6a266584e9c8efaf53dd82138aecbd662` baseline, main has gained
CI/guardrails, isolated domain contracts, persistence migrations, TurnEngine
extraction, deterministic routing/planner isolation, and Windows startup/CI with
Ollama reuse recovery (PRs #1–#10).

At the initial overlap check there were no open PRs. The original checkout was
on `yjv2/05a-semantic-tool-spec`, with uncommitted Core contracts/catalog, tests,
architecture/contribution instructions and README changes. This UX branch starts
from main in a separate worktree and edits none of those files. Root AGENTS.md
and CONTRIBUTING.md are deliberately left for the Core track to maintain.
Before publication, main was still at the same SHA and Core PR #11 had opened;
its nine changed files do not overlap this PR's four files.

## One releasable goal

Give the existing desktop controls a shared visual foundation, immediately used
by the current application:

- Tokens for color, surfaces, typography, spacing, radius, control dimensions,
  focus and interaction timing in `apps/desktop/src/design-system/tokens.css`.
- Native button, input, textarea, select and `.panel` primitives in
  `apps/desktop/src/design-system/primitives.css`.
- Existing `styles.css` imports both and retains feature layout and state styles.

This is a CSS foundation, not a new React component API. The existing native
elements already supply keyboard behavior and disabled semantics. Extracting
wrappers with no behavior would add an unused boundary at this stage.

Controls use opaque dark surfaces and visible borders. The existing `.secondary`,
`.active` and `.tiny` classes remain supported. Active buttons have an inset
underline as well as a distinct color; keyboard focus has a separate 2px cyan
outline with a 3px offset. Normal controls are at least 44px high; existing compact
buttons are at least 32px. Disabled controls do not get enabled hover feedback.
The recording-specific active appearance remains in the feature stylesheet.

`prefers-reduced-motion: reduce` disables decorative animations and transitions,
including the existing orb and background. No animation/transition completion
events drive application behavior. Forced-colors mode preserves active-button
distinction using a system-color bottom border.

## Using the foundation

Import `styles.css` once through the renderer entry point as before. It loads
tokens, then primitives, then feature styles. Use the existing native elements
and classes; keep layout in feature styles. Use the `--yj-*` tokens for these
shared values. Do not add speculative variants or unused tokens.

All fonts have local system fallbacks; no font, model or other asset download is
introduced. Legacy feature-specific colors, orbital decoration and layouts are
still present. This step is not a complete design-system conversion or an
accessibility certification of the whole application.

## Boundaries and compatibility

There are no changes to App.tsx, API clients, WebSocket handling, approval
decisions, voice lifecycle, startup, settings values, wire formats or persistence.
No runtime or development dependencies are added. CSS is shared across Windows
and macOS; it does not detect or call an operating system.

Application readiness without models, downloader/install behavior, hardware
detection, catalog/recommendations, ToolRuntime, policy, providers, audio and
packaging are outside this step. Existing readiness labels remain legacy state.

## Verification checklist

Run the existing complete checks from CONTRIBUTING.md. There is currently no
frontend component-test runner; this stylesheet change uses typecheck/build and
browser inspection instead of adding a new test framework or CSS string tests.
The PR records actual commands, results and any environment workarounds.

For visual review, use an isolated preview backend/runtime or the offline
renderer. Do not save draft settings into a personal database.

- Inspect Chat, Settings and the command palette at normal desktop and compact
  widths, including scrolling to the Settings footer.
- Tab across buttons and text fields: focus must be visible and distinguishable
  from the selected tab. Check the native voice select without saving a change.
- Check disabled chat controls while the backend is unavailable.
- Confirm control text and placeholder contrast against their opaque surfaces.
- With the OS/browser reduced-motion preference enabled, verify that backgrounds,
  the orb and button transitions stop; status text must remain visible.
- In forced-colors mode, check keyboard focus and the active-tab border.
- Repeat on macOS; a Windows browser check does not establish macOS/Electron,
  voice, model inference or packaged-app behavior. Mark unperformed checks NOT RUN.

## Proposed remaining YJUX-00 slices — not authorized here

1. YJUX-00B: application shell/navigation composition and responsive hierarchy,
   with current feature behavior preserved and a fresh Core overlap check.
2. YJUX-00C only if needed: remaining shared surface/status presentation, consuming
   existing backend states without inventing readiness or reasoning stages.

Chat and Settings redesigns retain their separate YJUX-05/06 scope; first-run
state and model setup remain YJUX-01 onward. Each later slice needs external
review of the preceding PR and explicit user authorization before implementation.

## Rollback

Revert this PR's commit to restore the prior stylesheet. No API, database,
configuration or model/data rollback is required. Do not delete runtime data.
