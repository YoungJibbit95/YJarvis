# YJUX-01 — Microphone Reliability & Intelligent Settings

## Gate and reviewed scope

YJCOM-03 PR #39 was merged. Initial `main` is `768e1ab0bf38db5e364251adfda1258adbb918dd`, with [7/7 successful post-merge Baseline CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37957167118), successful [Wiki publish/validation](https://github.com/YoungJibbit95/YJarvis/actions/runs/37957167087) and no competing PR. This patch is **YJUX-01 only**, with one PR and no DB migration, new agent architecture or changes to existing Voice wakeword/queue submission contracts.

## Initial microphone diagnosis

The prior `startVoiceMode` requested an unconstrained audio device through `getUserMedia`, did not let the user select an input or examine audio without a healthy STT endpoint, and the Electron main process had no explicit permission handler. These are *plausible* failure factors, not proven Windows-11/macOS hardware root causes. Windows need not show a separate microphone consent modal; Electron allowing Chromium access is not proof that Windows allowed device access.

## Electron, OS and origins

Electron 33 uses both `session.setPermissionRequestHandler` and `setPermissionCheckHandler` for complete media permission handling. The new pure tested boundary accepts only **audio-only** `media` requests from an actual top-level YJarvis webContents and exact trusted renderer origins (`app://yjarvis` packaged, `http://127.0.0.1:5173` developer). Camera, screen/display-capture, non-audio permissions and remote origins are never granted. No permissions are requested at startup. Native Windows/macOS denied or restricted microphone status is respected; the macOS `askForMediaAccess("microphone")` occurs **only** in response to an explicit audio request. The macOS electron-builder `extendInfo` now has `NSMicrophoneUsageDescription`, not a camera entitlement. App/IPC security remains unchanged apart from one authorized, read-only native permission-status request, which is itself origin-checked.

macOS TCC requires a bundled, correctly signed/packaged app for reliable OS-level confirmation. A prior denial may require OS settings and restart. Windows privacy controls for desktop apps can block capture even when Electron's Chromium callback returns true.

## Microphone preferences and independent diagnostics

The single active Settings UI allows selection of **Systemstandard** or real `navigator.mediaDevices.enumerateDevices()` entries of kind `audioinput`. Unknown labels are marked rather than invented. A small localStorage key stores the selected device ID only, with safe storage fallback; no new SQL table. Explicit selection goes to **the same `getUserMedia` constraints for Voice and diagnosis** with `deviceId.exact`; absent/unplugged IDs cause an explicit error rather than falling back. `devicechange` tracks removals and the existing Voice capture is stopped using the *manual*, non-cancel pathway so already recorded speech may finalize via its original ordered VoiceActivation queue. The device is never switched mid-recording. On native track ending, Voice closes with an actionable error. Previous Wakeword/Whisper/queue/TTS-echo suppression code remains intact.

The independent **Mikrofon testen** mode does not require Whisper, the chat Agent, a wakeword or an LLM. It obtains a real MediaStream, confirms one live audio track, resumes AudioContext, reads actual `AnalyserNode.getByteTimeDomainData` samples into an RMS live meter (not animated fake data), runs MediaRecorder, collects final `dataavailable` on stop and checks a non-empty audio Blob and detected level. No automatic upload and no persisted test audio. `Spracherkennung testen` is a second explicit step; if STT is ready it sends a short recorded Blob only to the **existing local** `/v1/audio/transcribe` and displays format, transcript, latency and errors. It never sends `/v1/chat`. Both paths stop tracks and close AudioContext on finish/error/unmount; no duplicate recorders. Errors distinguish NotAllowed, NotFound/Overconstrained, NotReadable, MediaRecorder/AudioContext, no-signal/empty data and STT connectivity. Device or input preferences are never mistaken for verified audio.

## Model and voice discovery

New read-only `GET /v1/setup/inventory` reuses the current settings and Ollama `/api/tags` semantics, with an HTTP timeout, response validation, no outbound downloads and `Cache-Control: no-store`. Actual chat model names, digests and sizes (when present) are shown as **installed**, and only an exact configured tag is marked **active**. An installed tag is explicitly **not evidence of successful inference**. Missing configured tags remain in the select as unverified; they are never silently replaced.

Whisper files are enumerated only in `runtime/models/ggml-*.bin` and the explicitly configured model path; installed status requires a non-empty regular file. The actual Whisper CLI/FFmpeg prerequisites reuse existing resolver/installer knowledge. Piper models are enumerated only in `runtime/models/piper/<voice>/` and the explicitly configured path, and require both non-empty `.onnx` and `.onnx.json`. Runtime presence does not prove synthesis/audio, which is still tested by existing GuidedInstaller verification and an explicit backend `speak` Hörprobe. macOS `say` is offered only where the actual `say` executable exists; its voice list continues to use the existing `/v1/audio/voices`. No fake output device picker is exposed because current Piper playback is controlled by backend/OS, not browser `setSinkId`.

The active `renderSettingsTab` now renders one connected `IntelligentSettings` view split into Spracheingabe, KI & Modelle, Sprachausgabe, System & Erweitert. Technical paths, free-form tags, safety allowlist and pronunciation remain available in advanced settings. Data sources have loading, empty, disconnected, retry and preserve-custom-value states. Dirty edits are flagged before Save; installing selected components merges only the SetupInstaller's `configured_fields` and retains unrelated unsaved changes. The existing `GuidedInstaller` and `ModelCatalogBrowser` are revealed on deliberate user action for verified installation, genuine progress, failure and cancellation. No second downloader, no silent model switches and no invented voice-quality claims.

## Manual Windows 11 hardware check — NOT RUN here

The GitHub Actions jobs use mocked Web MediaDevices and headless smoke tests, **not a physical microphone**. On a real Windows 11 system:

1. Start the installed YJarvis app. Open **Einstellungen → Spracheingabe**. Click *Geräte aktualisieren*, choose a named input or deliberately keep Systemstandard.
2. Click **Mikrofon testen**, allow access if requested, speak near the mic. Confirm the real meter changes; click **Test beenden & Aufnahme prüfen**. Require a live-track indication, detected signal and a non-empty audio Blob. If blocked, check Windows **Datenschutz & Sicherheit → Mikrofon → Mikrofonzugriff / Apps für den Desktop**. No Windows popup alone is **not** proof of failure.
3. With real whisper.cpp, FFmpeg and model installed, click **Spracherkennung testen**; speak, stop, check a transcript and actual `latency_ms` without any new chat message.
4. Start Voice in Chat. Say **„Jarvis“** plus a command. Verify a **single** submitted user message, correct wakeword ordering and no TTS self-echo. Change/remove selected microphone during recording and verify an orderly stop without a duplicate recorder.
5. Use **KI & Modelle** to refresh real Ollama models, choose an installed tag, and **save**; test an assistant reply. Use **Sprachausgabe** to select an installed Piper voice and save before **Stimme anhören**.
6. On macOS, repeat with a properly packaged `.app` and verify system **Datenschutz & Sicherheit → Mikrofon** (TCC). Test a prior denial and permission recovery after app restart.

**Manual Windows 11, macOS TCC, microphone, real Whisper and TTS hardware tests: NOT RUN.** Real performance measurements: **NOT MEASURED**. Mock tests validate control flow only.

## Remaining limitations and rollback

- Device labels/IDs can be hidden, unstable or reassigned by the OS; a missing explicitly chosen ID is an error, not auto-selection. Physical USB, virtual microphones, macOS TCC and Windows Desktop privacy switches require on-device validation.
- The read-only inventory is bounded to YJarvis-managed and configured model paths, not a global search. A valid-looking model file may still fail inference. Actual Piper audio is owned by backend/OS; selecting a browser speaker would be misleading.
- A future OS-specific output device selector, deep installer catalog integration or alternate audio provider would be a separate authorized step.
- Rollback after any future externally approved merge: revert only this PR. No user DB or model deletion. The desktop-only microphone preference in localStorage can safely remain unused.

**External review required after final green CI and diff check. STOP; no merge or next-phase work.**
