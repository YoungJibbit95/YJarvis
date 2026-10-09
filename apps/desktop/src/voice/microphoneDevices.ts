/** Shared microphone selection for Voice and diagnostics. Never silently fall back. */
export const MICROPHONE_PREF_KEY = "yjarvis.audio.input.v1";

export function readMicrophonePreference(): string {
  try { return window.localStorage?.getItem(MICROPHONE_PREF_KEY) || ""; }
  catch { return ""; }
}

export function persistMicrophonePreference(deviceId: string): void {
  try { window.localStorage?.setItem(MICROPHONE_PREF_KEY, deviceId); }
  catch { /* Private browsing / unavailable storage: session selection still works. */ }
}

export function microphoneConstraints(deviceId: string): MediaStreamConstraints {
  return {
    audio: {
      channelCount: 1,
      sampleRate: 48000,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      ...(deviceId ? { deviceId: { exact: deviceId } } : {})
    },
    video: false
  };
}

export function microphoneDeviceOptions(devices: MediaDeviceInfo[]): Array<{ id: string; label: string }> {
  return devices.filter((device) => device.kind === "audioinput" && device.deviceId !== "default" && device.deviceId !== "communications")
    .map((device, index) => ({ id: device.deviceId, label: device.label || ("Mikrofon " + (index + 1) + " (Name durch Betriebssystem verborgen)") }))
    .filter((device) => device.id.length > 0);
}

export function microphoneErrorMessage(error: unknown, platform: string): string {
  const problem = error as { name?: string; message?: string };
  const name = problem?.name || "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "SecurityError") {
    return platform === "win32"
      ? "Mikrofonzugriff verweigert. Windows 11: Einstellungen → Datenschutz & Sicherheit → Mikrofon; Mikrofonzugriff und Desktop-Apps zulassen prüfen. Auch Electron kann Windows nicht überstimmen."
      : platform === "darwin"
        ? "Mikrofonzugriff verweigert. macOS: Systemeinstellungen → Datenschutz & Sicherheit → Mikrofon → YJarvis. Nach einer früheren Ablehnung kann ein Neustart nötig sein."
        : "Mikrofonzugriff verweigert. Bitte die Browser-/System-Berechtigungen prüfen.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError" || name === "OverconstrainedError") {
    return "Das ausgewählte Mikrofon wurde nicht gefunden. Gerät anschließen und neu laden; kein automatischer Wechsel auf ein anderes Mikrofon.";
  }
  if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError") {
    return "Das Mikrofon konnte nicht gelesen werden. Es könnte von einer anderen Anwendung belegt oder vom System blockiert sein.";
  }
  return problem?.message || "Mikrofonfehler. Geräteanschluss, Betriebssystemrechte und Aufnahme-Unterstützung prüfen.";
}

export function audioRms(samples: Uint8Array): number {
  if (samples.length === 0) return 0;
  let squares = 0;
  for (const sample of samples) {
    const value = (sample - 128) / 128;
    squares += value * value;
  }
  return Math.sqrt(squares / samples.length);
}
