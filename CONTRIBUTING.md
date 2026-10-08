# Contributing to the YJarvis V2 migration

## Sources and scope

On 2026-10-08 the user explicitly authorized a separate **Windows installer
support** step: Windows x64 NSIS packaging, a bundled backend, installed process
startup/data placement and packaging checks. The user also explicitly requested
Ollama startup/reachability fixes, checking download endpoints, and replacing
the Electron menu/native frame with a custom macOS-style titlebar in this cycle. See
[Windows installer support](docs/architecture/windows-installer.md).
This overrides the packaging exclusion below only for that step; all other
roadmap and external-review gates remain in force.

User instructions take precedence, followed by the supplied
[V2 architecture](docs/architecture/YJarvis_V2_Architecture_and_Browser_Agent_Master_Prompt.md),
the explicitly approved roadmap step, and existing repository conventions.
The numbered roadmap and master prompt define the step order, subject to explicit
user decisions. The architecture is a target; it is not a reason to implement
later subsystems early. Read the accepted
[Windows/cross-platform addendum](docs/architecture/02_WINDOWS_CROSS_PLATFORM_ARCHITECTURE_ADDENDUM.md).
Windows 11 x64 is the primary current target; macOS Apple Silicon stays first-class
and Linux remains headless CI. Text/Core startup does not imply native tool/audio parity.

YJ2-00 through YJ2-05C2 and YJW-00A/B/B.1/01A/01B/01C are accepted. The current authorization is
**YJW-01D only**: one read-only Windows Start Menu application resolver, with no
app launch, Domain/Runtime coupling or provider registration.
Spec metadata/input/output contracts remain unchanged; application execution stays legacy.
See the [Windows application resolver note](docs/architecture/windows-app-resolver.md).
Adapters, production wiring, timeout enforcement, Observations, persistence/events,
planner/router changes, policy, apps/files providers, auto-discovery,
planner availability, macOS provider migration, audio, UI and packaging remain out of scope.
Architectural violations require a documented decision and explicit approval,
not an opportunistic refactor.

## One step, one branch, one pull request

Start from the inspected current `main`, compare it with the architecture baseline
`dea0e9e6a266584e9c8efaf53dd82138aecbd662`, and explain any intervening changes.
Never work directly on `main` or overwrite another contributor's work.

For the current step:

```text
Branch: yjv2/w01d-windows-app-resolver
PR: [YJW-01D] Add read-only Windows application resolver
```

Use the PR template in full. Keep changes narrowly reviewable and reversible.
Do not introduce new runtime dependencies unless the approved step needs them.
Never commit `.env`, credentials, model files, personal databases, or generated
build output. On 2026-10-07 the user explicitly authorized Codex implementation,
superseding only the historical agent/tooling restriction. Preserve the original
architecture source and all scope, evidence, safety and external-review gates.

Each cycle has one small, complete, independently testable and reversible goal.
Avoid WIP or aggregate PRs; split oversized proposed work before implementation.
Run focused checks and the complete existing suite/build, inspect the final diff,
remove unnecessary changes, open one PR, check CI, finish the handoff and stop.

## Checks and evidence

Follow [the development guide](docs/development.md). From the repository root,
with the project virtual environment active and dependencies installed:

```bash
python -m pip check
python -m pytest -q
python -m ruff check apps/agent/jarvis_agent tests
npm run test:startup
npm ci
npm run typecheck
node --check apps/desktop/electron/main.cjs
node --check apps/desktop/electron/preload.cjs
npm run build
```

Do not skip existing tests, add blanket error suppression, weaken TypeScript
options, or use `continue-on-error` to produce a green baseline. Ruff currently
checks a deliberately narrow correctness set, not formatting or every lint rule.
A renderer build and Electron syntax checks are not a packaged application test.
Record command, environment, result, and relevant CI run/check links. State
unperformed manual checks explicitly; never invent macOS or performance results.

## Review and stop gate

Before handoff, re-read changed files and the complete diff. Check scope,
compatibility, dependency changes, secrets, test evidence, and rollback. Document
nonblocking out-of-scope observations in the PR; fix only blockers within the
approved scope.

The required check names are `python-tests`, `python-lint`, `desktop-typecheck`,
`desktop-build`, `windows-python-tests`, and `windows-desktop-checks`. The workflow
runs on every PR targeting `main`, on pushes to `main` and migration branches,
and through manual dispatch, without path filters.

Repository files do **not** activate GitHub branch protection. At baseline,
`main` reported `protected: false` and no required status-check contexts. A
repository administrator should configure protection/rulesets separately to
require these six checks and review before merging; until then, these are
workflow and review conventions, not a server-enforced merge barrier. Do not
claim enforcement merely because a PR template or workflow exists.

The implementer must not merge the PR or enable auto-merge. After all
available checks are green, hand it to the user for external ChatGPT review
against the actual diff and the architecture, then stop completely. No next
branch, next PR, scaffold, or preparatory commit is allowed. CI success is not
user approval. Only explicit user authorization after external review unlocks
the next step. After YJW-01D, YJW-01E, apps.open, adapters, YJ2-05C3
and audio work remain blocked until explicit next-step approval after review.
