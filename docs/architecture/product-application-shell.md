# YJUX-00B — Application shell and responsive navigation

## Authorization and baseline

The user's external-review handoff explicitly accepts YJUX-00A and authorizes
YJUX-00B only after synchronization, merge and successful CI. This authorization
supersedes the older UI exclusion in the root Core contribution instructions for
this Product Experience step; it does not authorize changes to the Core track.

PR #12 was merged externally during synchronization, before the updated branch
could run its pre-merge checks. The user explicitly accepted the replacement
gate: six successful checks on both the synchronized branch and the merged main.
These gates completed before this branch was created:

- Synchronized `eedb149ad492a4f48a3bf7c15c904562a20e1d54`:
  [6/6 successful checks](https://github.com/YoungJibbit95/YJarvis/actions/runs/37689255058).
- Merged main / this step's base `1c9a338137c6211f88f88239d82cfb189d47ef7d`:
  [6/6 successful checks](https://github.com/YoungJibbit95/YJarvis/actions/runs/37689172860).
- `git diff --exit-code` confirmed identical trees. Synchronization added no UX
  change. Main includes accepted Core PR #11 and Product Experience PR #12.

At the start of this step there were no open Core PRs. Uncommitted work in the
original checkout was limited to README and backend domain/input contracts,
fixtures and tests on `yjv2/05b1-typed-tool-inputs`. No desktop files overlapped.
This branch reuses the separate Product Experience worktree and starts directly
from the inspected main, without rewriting or modifying the Core checkout.

The pre-publication check found Core PR #13 (`yjv2/05b1-typed-tool-inputs`)
open at `88e22a5`. Its ten files cover contribution guidance, domain contracts,
architecture notes and tests/fixtures; none overlap this step's five files.
The original checkout had only an uncommitted README change. Main remained
`1c9a338`; no Core file or concurrent user change was modified by this step.

## Ownership

`apps/desktop/src/app/AppShell.tsx` contains small presentational components:

| Component | Responsibility |
| --- | --- |
| `AppShell` | Frame, skip link and labelled main content viewport |
| `AppHeader` | Product identity and global command entry |
| `GlobalCommandTrigger` | Native button invoking the existing open callback |
| `RuntimeStatus` | Display existing formatted values in a native disclosure |
| `PrimaryNavigation` | Four native buttons and the selected-area indication |

App still owns active-tab state, its existing transition callback, command
palette state/commands, all feature rendering and every runtime interaction.
The shell receives children, formatted status values and callbacks. It has no
effects, hooks, API calls, subscriptions or persistence. `TabId` retains exactly
the same four values. Command Palette remains owned and rendered by App.

## Presentation and responsive behavior

The shell consumes the existing YJUX-00A tokens and native primitives. Its own
layout lives in `app/app-shell.css`. Only shell styles and outer decorations were
removed from `styles.css`; feature rules and the conversation orb remain there.
The outer frame now uses a restrained static background instead of the animated
grid/noise/header orb. No new animation, assets or dependency is introduced.

Wide windows use a side navigation; at 1180px and below it becomes a row above
the content, and at 620px and below it wraps into two columns. All four areas
remain available: Chat, Approvals, Settings and Smart Home. No Setup or Models
destination is added. Short windows can scroll the frame instead of collapsing
the content away. The compact chat-view boundary contains its existing sticky
descendants, so the viewport can scroll the full feature without covering its
header/messages. Long code/path values wrap within the content viewport.

Runtime details are closed initially. Core mode and model remain in the summary;
the narrow summary omits the model, which is still available by opening details.
Voice Input, Core, UI Render, Reply Mode, Model, STT, Session and the former client
environment label retain their existing values and formatting. `idle` is not
translated into a health verdict. There is no new ready/degraded state, model
detection, health calculation or inference from human-readable status messages.

Navigation uses native buttons inside a named `nav`, with `aria-current` and a
labelled `main`. It intentionally does not claim the ARIA tabs keyboard pattern.
Existing Tab/Enter/Space behavior and App's Ctrl/Cmd+K listener remain. A skip link
moves keyboard focus to the main region. Focus remains visible for the added
link, disclosure and main region; the existing reduced-motion foundation stays.

## Verification and limits

Run all existing CONTRIBUTING checks. The PR contains exact commands, final-head
CI links and environment details. No new frontend test framework is introduced.
Source comparison verifies unchanged feature logic/render functions and Command
Palette props; backend, API clients, settings persistence and approval execution
are absent from the diff.

Windows renderer verification uses a real isolated backend and temporary SQLite
runtime with a local Vite proxy, without altering product API configuration.
The four areas are exercised at normal, maximized, compact, narrow and short
sizes. Check navigation/active state, content labels, horizontal overflow,
keyboard focus, status disclosure, skip link and Command Palette. A local time
question exercises existing deterministic text chat with voice replies off;
it does not establish LLM inference or voice support. No approvals are executed
and no settings are saved during the shell check.

Electron smoke is NOT RUN when the installed Electron binary is unavailable.
macOS/Apple Silicon, high-DPI hardware, audio and packaged-app verification are
NOT RUN here. The existing Windows voice-list error remains visible; this step
does not hide or repair it. Existing npm audit findings remain outside scope.

## Stop gate and rollback

This step covers only shell/navigation composition and responsive hierarchy.
Chat, Settings, approval and voice redesigns, setup/readiness, models/downloads,
Core/ToolRuntime/policy/providers, backend APIs and packaging remain out of scope.
No YJUX-00C or YJUX-01 work starts after this PR. External review and explicit
authorization are required again; green CI is not approval.

Revert this PR's commit to restore the former shell. There is no data, settings,
API or database migration, and rollback must not delete runtime data.
