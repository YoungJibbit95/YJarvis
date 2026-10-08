# Guided local setup (Windows installed desktop)

Explicitly authorized on 2026-10-08: installation buttons for local models,
voices and required components, automatic first-run configuration and additional
UI motion. The user requested that these be delivered together in one reviewable
step, superseding the earlier suggested split. Base: main `37deeea` (merged #32).
This does not authorize subsequent provider/planner/policy migration work.

## User flow

The first walkthrough offers a complete selection and individual install buttons:

- Chat: any syntactically valid Ollama library model tag; default
  `qwen2.5:3b-instruct`. Non-completion and cloud-backed models are rejected.
- Speech input: Whisper tiny/base/small/medium/large-v3/large-v3-turbo; default
  small. Missing Windows whisper.cpp and FFmpeg are downloaded automatically.
- Speech output: the official live Piper voice catalog, including multiple
  languages/quality variants; default German Thorsten medium. Model, matching
  config and available model card are installed together. Multi-speaker models
  use their default speaker.
- Ollama: reuse/start an installed server, or install the official standalone
  Windows x64 CLI/library ZIP if absent. No administrator/system installer or
  system-wide PATH mutation is required. Frozen backend redistributable DLLs
  supply native helper runtime dependencies via the process PATH.

All selections can be installed with one button. The UI shows the current
download's byte progress and verification stages, supports cancellation/retry,
and refreshes readiness after configuration. The existing app loads the new
settings on entry. The same controls remain available in Settings afterward.
Selected model fields update; language/allowlists/other settings are preserved,
including unrelated unsaved settings drafts.

A local browser flag records walkthrough entry; existing models do not skip the
first walkthrough until the user enters or completes setup. Rechecks after
successful installation can enter the ready/degraded app automatically. Existing
read-only readiness DTOs stay unchanged: e.g. a model file alone does not certify
a working speaker. A selected voice runs an announced short output probe before
activation. Its path/size/mtime verification record allows the read-only status
route to report the successful setup test; changed/replaced assets invalidate
that record. Existing read-only inspectors remain conservative without this
explicit test evidence. The explicit "Stimme testen" button also uses the actual TTS path.
Microphone access still requires the normal operating-system/browser permission.

## Runtime and acquisition boundaries

`setup_installation.py` owns one explicit job and its small JSON journal, outside
turn orchestration. `setup_components.py` owns reviewed acquisition recipes;
`setup_downloads.py` owns bounded, verified transfers/extraction. The new
`/v1/setup/install` transport is separate from semantic tools and planner routing.

- POST starts a selection, GET reads status, DELETE requests cancellation.
- GET `/options` fetches supported voice/Whisper choices. Failed catalog reads
  allow retry and a clearly labelled default voice choice, not invented success.
- Every mutation requires an explicit trusted desktop/dev Origin. Arbitrary
  browser origins and missing Origin are rejected. No generic URL, shell command,
  executable path or installation destination can be passed through this API.
- Ollama operations target only the configured local HTTP endpoint. External,
  credential-bearing or proxied-path endpoints are rejected for setup.
- Binary/weight downloads verify SHA256 and byte size from official GitHub
  release metadata or Hugging Face LFS metadata. Immutable HF revisions pin
  model/config files; small Git blobs verify their Git content identity.
- HTTPS redirects are restricted to source/CDN domains. Transfers cap sizes,
  check disk space, stage `.part` files and publish atomically. ZIP members are
  preflighted for traversal, drives, links and excessive unpacked sizes.
- Downloaded Windows programs live under runtime/tools, not Program Files.
  Full ZIP contents preserve DLLs/licenses. Only a validated executable location
  is recorded in the tool manifest. A process-local FFmpeg path is restored on
  restart; owned standalone Ollama servers are cleaned up on backend shutdown.
- Installed model caches remain after cancellation or a later component failure;
  selected settings do not become active until the complete request succeeds.
  An atomic SQLite compare-and-write rejects concurrent settings changes.
  The brief final settings commit finishes atomically and cannot be half-cancelled.
- Restart marks an unfinished job interrupted; it does not silently download or
  restart the request. Retrying reuses verified files/Ollama's partial-download cache.
- Packaged startup refuses an already occupied backend port before spawning,
  rather than silently reusing an already listening app's database for installation requests.
  Explicit external-backend management retains its previous opt-in behavior.

Chat installation verifies pull completion, local completion capability and a
real text generation. Whisper loads the selected model using a disposable silence
WAV and the actual installed CLI. Piper loads the selected model and synthesizes
a disposable WAV before activation. Windows/Linux playback uses existing
sounddevice/soundfile dependencies; macOS retains the original `afplay` path.

No new runtime dependency, DB schema, wire/spec model, approval behavior,
provider registration, availability grant or planner capability is added. The
existing catalog endpoint remains descriptive/read-only.

## Motion

Walkthrough sections, panels, message arrivals, command dialogs and controls get
short CSS transitions. Streaming drafts do not restart an arrival animation for
each token. Existing `prefers-reduced-motion` behavior remains enforced; no
application lifecycle depends on animation events.

## Checks and limits

Run the existing full suite/build plus:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_guided_setup.py
node --test tests/desktop/guided-setup.test.cjs
npm run dist:win
npm run test:packaged-backend
```

CI tests deterministic mocked acquisition failures, SHA/cache/ZIP safety,
cancellation, conflict rejection, origin checks, first-run choices and status
validation. CI does not download multi-GB models or certify microphones/speakers.
Real Windows acquisition/inference/voice evidence and limitations are recorded in
the PR. No macOS audio integration result is inferred from Linux/Windows tests.

Official latest Ollama/FFmpeg releases are resolved at explicit installation
time; whisper.cpp is pinned to v1.8.3. Resulting assets are SHA256 verified.
Future upstream availability, model licenses, device permissions/drivers and
hardware capacity can affect a selection. Failed verification is reported rather
than activating the selection. System program acquisition on macOS/Linux is
left to the documented package-manager setup; this release's complete program
bootstrap targets Windows x64. Existing unsigned-installer/npm-audit risks remain.

Rollback: revert this step to restore the earlier walkthrough/playback behavior.
Preserve personal DB/model/runtime data. No downgrade/schema migration is needed.
Do not remove a shared system Ollama installation or cached user models.
