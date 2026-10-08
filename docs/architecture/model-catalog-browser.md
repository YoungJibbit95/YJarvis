# YJUX-02B: read-only model catalog browser

The setup screen and existing in-app setup disclosure now show the accepted
[bundled model catalog](model-catalog.md). This step adds information browsing,
without model selection, installation or readiness changes.

## Baseline and review gate

Base main: `210da7cd5f3f104af40ef07a24c9aba0564a4f32`. The user's explicit
Product Experience authorization applies independently of the Core-step labels
in AGENTS.md and CONTRIBUTING.md. Before this branch began:

- Core #18 squash main `b275eb6`: [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37748981079).
- Product #17 synchronized head `dd2eb39`: exactly the six #18 files added,
  unchanged Product patch; [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37749222209).
- Product #17 squash main `210da7c`: identical combined tree;
  [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37749451856).

Relative to architecture baseline `dea0e9e`, main includes the accepted CI,
domain/persistence/orchestration extractions, Windows startup, typed capability
contracts and semantic catalog, Product foundations/shell/readiness and the
offline model catalog. Core #19 (YJ2-05C1) changes its runtime kernel, Core tests
and guidance only; its inspected file list has no overlap with this step.
The concurrent Core checkout and its README edit are untouched.

## Transport and validation

`GET /v1/setup/models` returns the existing immutable `BUNDLED_MODEL_CATALOG`
through the Pydantic `ModelCatalog` response model. It accepts no catalog input
and performs no settings, database, readiness, network, hardware or process
operation. POST/PUT/PATCH/DELETE/HEAD return 405. Existing `/v1/setup/status`
behavior and its readiness authority are unchanged.

The renderer fetches this endpoint only when the catalog disclosure is open.
An eight-second abort timeout, request cancellation on close/unmount, and a
catalog-only retry keep failures separate from setup readiness. Transport and
malformed-data failures show an explicit browse error without replacing status,
changing chat availability, or updating settings.

`parseModelCatalog` validates the received JSON before rendering: exact fields,
nonempty text/entries, unique catalog and backend/model identifiers, accepted
categories/backends/acquisition pairs, HTTPS source metadata and calendar dates,
mechanism-specific acquisition hosts, license scopes and required model license,
and positive safe-integer size/context values. Nullable metadata remains null;
context is chat-only. Unknown fields or future backend variants require an
explicit reviewed contract extension. The renderer holds no copy of the three
bundled entries; its tests use synthetic fixtures.

## Presentation and boundaries

Cards show category, name, description, publisher, backend, known approximate
decimal download size, publisher context and scoped license metadata. Unknown
Thorsten model-weight licensing is shown as "Nicht eindeutig angegeben";
dataset CC0 is displayed separately. Unknown size is omitted. These are dated
catalog facts, not installed state, hardware suitability or runtime configuration.

Native disclosures contain identifiers and source publishers, dates and URLs.
The existing Electron entry points do not define a reviewed external-navigation
boundary, so URLs are selectable, noninteractive text. No anchors, shell commands,
model action buttons or card selection handlers are introduced. Existing design
tokens and setup styles supply the layout and keyboard focus indication.

## Verification on Windows, 2026-10-08

- Python: full suite 1006 passed; focused catalog/API/readiness suite 198 passed;
  pip check and repository Ruff check passed.
- Node: 36 DTO/presentation tests and 22 startup tests passed. CI runs the new
  DTO/presentation tests in both Linux and Windows desktop checks.
- `npm --script-shell=powershell.exe ci`, typecheck, production build and both
  Electron entry-point syntax checks passed. The process-local npm shell option
  accommodates this host's PATH; no package script or dependency was changed.
- Windows browser renderer with the real backend/catalog, isolated temporary
  database and controlled empty Ollama inventory: first run, all three categories,
  scoped/unknown licenses, sizes only for Qwen/Whisper, keyboard disclosure,
  normal-app reopening, malformed-response error, successful retry and timeout
  were verified. Missing-model chat controls remained disabled.
- At 1320x860, 960x760 and 480x780 there was no horizontal overflow, including
  expanded source URLs at narrow width. The complete setup-status JSON and
  logical SQLite dump were identical before/after first-run browsing.
- Electron GUI, real-model inference/audio, macOS/Apple Silicon, HiDPI and
  packaged application checks: **NOT RUN**. Browser renderer verification and
  syntax/build checks do not establish native integration.

The endpoint test compares the response with the Python bundle, blocks network,
process, common filesystem-write and settings/readiness boundaries, and checks
unchanged real temporary database/settings after GET and unsupported methods.
DTO tests reject malformed metadata; presentation tests cover licenses, loading,
errors and absence of action links/buttons. Request lifecycle and readiness
independence also have the manual evidence above.

## Risks, exclusions and rollback

Existing npm audit reports 21 dependency vulnerabilities; this step changes no
dependencies. An initial npm ci hit an esbuild lock while Vite was running;
stopping the owned preview resolved it and the full install/build passed.
The normal-app preview also exposed the existing unavailable Windows voice
executable path; audio repair remains outside this step.

Hardware scans/ranking, downloader/installation/removal, progress/manifests,
settings auto-selection, audio repair, packaging and Core ToolRuntime remain
out of scope. Revert this step's commit to remove the browse UI, route and tests;
there is no migration or personal/runtime/model data to clean up. External
review and explicit user authorization are required before any next YJUX step.
