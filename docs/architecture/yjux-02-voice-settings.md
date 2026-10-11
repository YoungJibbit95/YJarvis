# YJUX-02 — Voice recovery and settings redesign

## PR #43 external review correction

The first PR #43 head left two gaps in microphone evidence handling. The
Settings view owned the tested device ID, while its `devicechange` listener
existed only inside the conditional microphone diagnostic. A system-default
change on another Settings page could therefore leave the overview claiming
an old hardware success. Settings now listens for device changes throughout
its own mount, invalidates the proof even when the selected ID is empty, and
passes a device revision to the diagnostic. Listener cleanup follows the
Settings and diagnostic mount lifetimes, including React StrictMode replay.

A device event during a capture previously cleared the parent proof without
ending the recorder generation; a later `onstop` could restore it. The
diagnostic now invalidates the generation synchronously, stops the recorder,
releases tracks, AudioContext and timers, and clears access, signal, format,
transcript and result displays. Delayed recorder callbacks and pending media
requests cannot restore evidence for a previous device. Device selection,
OS denial/restriction, access failure and recorder error use the same
fail-closed state. A new user-started RMS plus nonempty Blob test restores
readiness. A Whisper-only transcription failure after such a capture leaves
the independent hardware proof intact while reporting the Whisper failure.

ReactDOM StrictMode tests exercise the real Settings and microphone component
mounts, section changes, listener cleanup, default-device invalidation,
permission revocation and retesting with simulated MediaDevices. Focused
recorder tests delay `onstop` after a device event and verify that no stale
success appears. These tests do not exercise physical devices, packaged OS
privacy prompts or actual microphone audio; those remain **NOT RUN**.

## Post-merge review corrections

PR [#41](https://github.com/YoungJibbit95/YJarvis/pull/41) was merged into
`main` as `666a9da0482b9b9cd84c1159f4300a46e951bc6b` on 2026-10-11.
The [post-merge baseline](https://github.com/YoungJibbit95/YJarvis/actions/runs/38127668435)
and [Wiki workflow](https://github.com/YoungJibbit95/YJarvis/actions/runs/38127668441)
passed. Two subsequently supplied MEDIUM review findings require a separate,
explicitly authorized follow-up PR from that main SHA.

1. `switchTab` now returns whether leaving Settings was accepted. The Settings
   Voice-test callback starts the existing Voice path only after acceptance.
   A rejected dirty-draft confirmation keeps Settings visible and makes no
   microphone request. The existing in-flight guard still prevents duplicate
   starts; Chat and Command Palette navigation use the same decision function.
2. Settings owns one current-device hardware proof, passed to the microphone
   diagnostic on every mount. Only measured RMS plus a nonempty MediaRecorder
   blob set it. A selected-device change, OS `devicechange` (including a changed
   system default), reported denial/restriction, or failed audio access/capture
   clears it. A Whisper transcription failure after a verified recording does
   not erase that independent hardware proof. Permission granted by itself
   never sets it. Access, signal, recorder and Voice-test readiness display the
   same proof after switching away and back.

The follow-up UI check used the live Vite renderer and a separate temporary
local backend on macOS at a 663×695 browser viewport. All five Settings areas
were reachable; inventory-backed installed/installable states and Save/Discard
were visible. At this compact size, navigation labels originally broke inside
four narrow columns and the diagnostic content had only 68 px of scroll height.
The responsive correction uses wider navigation buttons and one outer scroll
area with a sticky Save/Discard footer. No install, save, microphone, Whisper,
Voice or speaker action was triggered during this visual check. The browser
preview has no packaged Electron permission path, so it is not hardware proof.

Focused regression tests cover rejected/accepted Voice navigation, one capture
start, Settings section round trips, device selection/disconnect, OS revocation,
permission granted without proof, no signal, empty blob, Whisper failure and
recorder concurrency. Full command results and final-head CI belong in the
follow-up PR handoff. Native Windows/macOS microphone hardware, OS privacy UI,
live USB hot-swap, real Whisper/wakeword and speaker playback remain **NOT RUN**.
The follow-up PR can be reverted on its own without deleting profiles, runtime
databases, models, audio assets or user settings.

## Verified start gate

- YJUX-01 PR #40 merged; original main: `16da0c0d72abaa14dfb4d19c394fe7274c2c8dd9`.
- [Post-merge Baseline CI #38045721122](https://github.com/YoungJibbit95/YJarvis/actions/runs/38045721122): 7/7 green on exact starting main; [Wiki #38045721172](https://github.com/YoungJibbit95/YJarvis/actions/runs/38045721172): success; no open PR when branch was created.
- One authorized branch: `fix/yjux-02-voice-recovery-settings-redesign`. No new V2/LLM runtime, DB migration, generic OS/shell actions, downloader, Voice/approval policy changes.

## P0 — Actual causes and recovery

**React.StrictMode:** `MicrophoneSettings` previously initialized an `alive` ref to true, set it false in a cleanup, but never reset it on the next effect setup. With the actual `React.StrictMode` extra setup/cleanup/setup sequence during development, a newly clicked microphone test could receive a valid `getUserMedia` stream yet bail out without starting a recorder. The corrected setup sets the ref true on each mount/effect reactivation, invalidates stale async attempts with a generation, and performs idempotent cleanup of tracks, MediaRecorder, AudioContext, source node and timers. A synchronous pending-start lock guards duplicate capture before React state has committed. A finite MediaRecorder finalization watchdog avoids a permanently pending `finalizing` state.

**Stale Voice selection:** The Command Palette previously memoized `startVoiceMode` without the selected device in dependencies. The corrected `App` holds a single current `selectedMicrophoneIdRef` used by the async Voice capture and updated synchronously when settings change; the memo dependency is also updated. Chat, Command Palette, TTS resume, starts after device changes and Wakeword capture use the same latest exact `deviceId`. The legacy VoiceActivation ordering/queue and TTS echo suppression remain unchanged.

**Permission recovery:** The Settings microphone section presents independent OS status, an actual access attempt, and tested hardware evidence without conflating them. *Mikrofonzugriff anfordern* calls Chromium's audio-only `getUserMedia` after a real click, verifies a live track, and releases tracks immediately, without Whisper, Chat or an active recorder. *Berechtigung erneut prüfen* refreshes OS status/MediaDevices without secretly recording; returning to the app also refreshes inventory. *Betriebssystem-Einstellungen öffnen* passes no URL or command: the origin-checked Electron main process opens the fixed Windows `ms-settings:privacy-microphone` URI or a fixed macOS System Settings route with app fallback. No arbitrary external URI or general OS process execution is exposed. Electron 33 audio-only trusted-origin permission handlers, macOS TCC and `NSMicrophoneUsageDescription` from YJUX-01 remain authoritative; previously denied macOS permission cannot be forced by the app.

**Diagnostic progression:** A small progressive checklist follows OS access → actual track/RMS → real MediaRecorder/blob/MIME → optional Whisper transcript (no Chat) → consciously starting the established Jarvis Voice/Wakeword flow. A missing device inventory *before permission is granted* is not automatically called a disconnected microphone. The read-only UI only records statuses and measurements, no audio or transcripts persist to a diagnostic log. The test mode never sends audio to Whisper without a separate explicit STT click.

## Manual on-device verification (not yet performed)

**Windows 11**: open packaged YJarvis → Settings → Spracheingabe → check OS status → deliberately click `Mikrofonzugriff anfordern` → speak into chosen device and run `Mikrofon testen`; verify live RMS, nonempty recorder bytes, proper MIME. Run separate Whisper test only when setup reports required binary/model/FFmpeg, confirm transcript without Chat, then start `Jarvis hören lassen` and say wakeword + command; confirm exactly one Chat request. While running, unplug USB mic/change device and verify controlled stop/no duplicate recorders. Deny Windows desktop-app mic access in Windows Settings and verify errors and recovery after re-enabling. **macOS**: repeat from correctly packaged, TCC-enabled `.app` with first grant and prior denial; verify System Settings + app restart.

**HARDWARE TESTS: NOT RUN** on these CI runners. React/AudioContext/MediaRecorder tests are mocked hardware but actual React effects are exercised via ReactDOM StrictMode in targeted integration test. Real microphone, OS privacy UI and physical TTS echo behavior require a device. No latency invented.

## P1 — Implemented Settings workbench and actionable model/voice discovery

The previous YJUX-01 Settings view had a horizontal tab row and many technically
accurate but largely form-based selectors. The **active** App component continues
to render exactly one `IntelligentSettings` instance. YJUX-02 makes it a
responsive workbench with a compact sidebar and a real **Übersicht** landing page.

The Übersicht contains four source-backed status cards:
- **Mikrofon:** default vs user-selected device, plus "hardware not tested" until
  an actual successful local MediaRecorder test in the current Settings session.
  Changing/disconnecting a selected device invalidates that evidence.
- **Chat-Modell:** active **saved** model, count of models reported by the
  configured Ollama `/api/tags` inventory and backend reachability. Presence
  is explicitly **not** successful inference.
- **Spracherkennung:** existing Setup readiness plus actual Whisper CLI and
  FFmpeg presence. Being found does not imply a successful recording.
- **Sprachausgabe:** known paired Piper voice files and saved backend engine.
  Playback remains unverified until the user requests an actual preview.

Each card navigates directly to a related workflow. The independent
**Spracheingabe** page still mounts the actual `MicrophoneSettings` component
with permission recovery, actual media-device selection, audio analyzer/recorder,
separate Whisper upload and the existing explicitly activated Wakeword test.

The **KI & Modelle** page includes searchable selection cards for the real
installed Ollama models and a separate catalog-derived set of models which
are *known/installable but not currently installed*. Cards show the exact
backend ID and size only when the source supplies it. The existing native
select remains as an accessible fallback; selecting only updates
`settingsDraft`, never the saved model.

The **Whisper** page has separate cards for verified present model *files*
and supported models from `fetchInstallOptions`. The latter are explicitly
uninstalled choices, not imaginary local assets. Whisper status continues to
come from the existing setup/readiness checks.

The **Sprachausgabe** page offers cards for full Piper `.onnx` +
`.onnx.json` pairs reported by `/v1/setup/inventory`, the previously supported
macOS `say` voices and a searchable subset of the existing Piper
`/v1/setup/install/options` catalog. A voice is not reported as successfully
heard just because its files exist. An explicit `speak` preview uses the
**saved** engine and voice; unsaved selections must be saved before preview.

**Installation** is still the existing `GuidedInstaller` and
`SetupInstaller`. An install card opens the same in-page install workspace
with one verified catalog ID preselected, but **never starts a download on
opening**. The user still explicitly presses the existing Install button,
with the same progress/cancellation/verification and error behavior. Existing
model catalog license/source details are accessed through the same
`ModelCatalogBrowser`. No new installer, package sources or V2 runtime wiring
was created.

**Drafts and security:** Settings navigation does not discard a draft.
The persistent footer shows dirty/saving/error/saved states, provides
`Änderungen speichern` and `Verwerfen` controls and displays save
errors without faking success. Navigating to a different *app* tab with a
dirty draft invokes an explicit confirmation where available. Custom model
tags, original technical paths, pronunciation and file access allowlists
remain in **System & Erweitert**. The existing installer `configured_fields`
mechanism merges only expressly installed component values; unrelated
unsaved preferences are not silently replaced. No SQL migration or arbitrary
file scan is introduced.

### UI and regression verification

- Desktop tests exercise the live Settings component through the existing
  React test harness: overview/click-through, actual inventory-based choice
  cards, verified catalog-only install choices with no automatic save/install,
  missing/offline model, Whisper/Piper cards, saved voice preview gating,
  save/discard and preservation of custom allowed paths, plus retry/error.
- StrictMode tests use real ReactDOM `StrictMode` setup-cleanup-setup with
  temporary global property **descriptors** restored even when a test fails.
  Audio meter simulation is executed inside React `act()` so the actual
  analyzer state reaches the rendered DOM.
- The Windows packaging VM loads the **real**
  `microphone-recovery.cjs` into Electron's main process, with a fixed
  Settings URI shell mock and positive/negative trusted-webContents IPC tests.
  Camera, screen capture and arbitrary URI execution remain blocked.

PR #41's final-head [baseline CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/38099865798)
and [Wiki validation](https://github.com/YoungJibbit95/YJarvis/actions/runs/38099865823)
passed; follow-up PR evidence is recorded separately.

## Verification boundaries and rollback

Physical Windows 11 privacy settings, real microphone input and USB hot
unplug, macOS packaged TCC, actual Whisper/Wakeword and speaker output were
**NOT RUN** in this connector-only environment. Do not mistake headless
React/MediaRecorder mocks or installer smoke for real audio hardware.
The on-device instructions above remain required before claiming full
microphone reliability on a specific computer.

To roll back the already merged YJUX-02 work, revert PR #41's merge commit.
The separately authorized review corrections can be reverted independently.
Neither rollback deletes user databases, saved profiles, local Ollama models,
downloaded Whisper/Piper assets or voice history. The follow-up still requires
independent external review before merge.
