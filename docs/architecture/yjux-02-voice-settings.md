# YJUX-02 — Voice recovery and settings redesign

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

## P1 redesign and final CI

(To be completed in the next commit on this same branch. No premature PASS until a real 7/7 PR-head Baseline CI and successful Wiki validation.)
