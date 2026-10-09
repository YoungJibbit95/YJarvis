# YJBASE-01 — restoring the accepted CI baseline after PR #34

## Starting evidence

- Last fully green main: `2537e9362f2aeb97b3a07e80fb11f9156a56b994`, Baseline CI `37820991682` (7/7).
- Regression main: `a23613aef7fa6973304b0db39fdd7b923599a0a4`, Baseline CI `37910261897` (2/7). Wiki CI `37910261952` succeeded.
- PR #34 is the only commit between those SHAs. Its macOS packaging change includes unrelated, not-yet-integrated development files and tests.
- There were no open PRs when YJBASE-01 started. No local runtime data or README is changed.

## Classification and minimal corrective scope

| PR #34 additions | Classification | YJBASE-01 decision |
| --- | --- | --- |
| `apps/desktop/package-mac.mjs`, `apps/desktop/electron-builder.cjs`, `apps/desktop/electron/packaged.cjs`, macOS build guidance | macOS packaging path | Preserve unchanged |
| `native_tools.py`, macOS/Homebrew tool discovery in `audio.py`, `setup_components.py`, `setup_readiness.py` | Integrated native tool discovery | Preserve unchanged; existing tests retained |
| `App.tsx` partial transcription preview and AudioContext resume | Current voice behavior, later YJVOICE-01 responsibility | Preserve unchanged, even if reliability work remains |
| `persistence/schema.py` recognized legacy metrics table plus migration tests | Independently tested legacy database adoption | Preserve unchanged; do not add a new metrics migration |
| `execution_engine.py`, `tools/capability_tools.py`, `tools/providers/*`, `system_telemetry.py` | Isolated preparatory modules, not production-wired | Preserve the code and passing tests; no registration |
| `apps/agent/jarvis_agent/intents/*` | Incomplete, unregistered replacement router requiring a `ToolCallIntent.confidence` contract absent from the accepted runtime | Keep source unregistered. Do not change the legacy intent contract or wire a new router |
| `apps/desktop/src/components/*`, `apps/desktop/src/index.css` | Unintegrated alternate React UI; imports missing `motion/react`, `lucide-react`, `LearningOverview`, `PerfOverview`, and absent UI settings | Preserve every file. Exclude only `src/components` as independent TypeScript roots; imported modules will still be checked by TypeScript. No new product dependencies/contracts |
| `tests/test_agent_service_settings_cache.py` | Speculative cache/invalidation feature: no `AgentService._get_settings` or invalidation contract exists | Withdraw PR #34's unimplemented-feature test from the accepted baseline |
| `tests/test_intent_router.py` | Tests unregistered experimental router requiring unapproved `confidence` on `ToolCallIntent` | Withdraw PR #34's unimplemented-feature tests; preserve experimental code for separately approved integration |
| `tests/test_learning_engine.py` | Tests unimplemented multi-step follow-up and recovery features | Withdraw PR #34's unimplemented-feature tests |
| `tests/test_perf_metrics.py` | Tests nonexistent per-run metrics DB API and `get_perf_overview` endpoint | Withdraw PR #34's unimplemented-feature tests; keep the independently valid legacy adoption test |
| `package.json` | Accidental loss of five existing scripts while adding `dist:mac` | Restore exact commands from last green main; retain `dist:mac` and committed dependency manifest/lockfile |

These four withdrawn Python test modules were **introduced by PR #34**, not part of the previously green accepted test baseline. They asserted features that PR #34 did not implement and that were never wired to the application. The deleted tests remain inspectable in the immutable PR #34 diff and can be reintroduced alongside proper contracts and implementation in an explicitly approved step. This is **not** a skip, a fake passing assertion, or removal of any previously passing accepted test file.

## Guardrails and future integration

The production renderer remains `src/main.tsx` → `SetupGate` → `App.tsx` and its `app/` and `setup/` components. TypeScript still covers these modules and all their imports. A regression test rejects imports of quarantined `src/components` from the live source tree; a future integration must explicitly update the compiler scope and supply real dependencies, types, API support and tests.

The existing FastAPI `AgentService` uses `LegacyRouting` and retrieves settings from `Database` during runs. No cache API, new multi-step planner, per-run metrics endpoint or new DB migration is introduced by this recovery. Tests covering accepted domain contracts, learning behavior, persistence/migrations, routing, setup, tools, native helpers, startup and packaging remain active.

Do not infer working microphones, model downloads, TTS, Apple Silicon package creation or full macOS integration from headless Linux/Windows CI alone. YJVOICE-01 remains blocked until this recovery is externally reviewed, merged by the user, and the new main CI is green.
