export type InstallSelection = { chat_model: string | null; whisper_model: string | null; voice: string | null; install_ollama: boolean };
export type InstallField = "model_name" | "tts_engine" | "tts_model_path" | "tts_voice" | "whisper_model_path" | "whisper_binary";
export type InstallState = { status: "idle" | "running" | "completed" | "failed" | "cancelled" | "interrupted"; id: string | null; stage: string; completed: number; total: number | null; error: string | null; configured_fields?: InstallField[]; cancellable?: boolean };
export type InstallOptions = { whisper_models: string[]; voices: { id: string; name: string }[] };

export function parseInstallState(value: unknown): InstallState {
  if (!value || typeof value !== "object") throw new Error("Ungültiger Installationsstatus");
  const data = value as InstallState;
  if (!["idle", "running", "completed", "failed", "cancelled", "interrupted"].includes(data.status)
      || typeof data.stage !== "string" || !Number.isSafeInteger(data.completed) || data.completed < 0
      || (data.total !== null && (!Number.isSafeInteger(data.total) || data.total < 0))
      || (data.error !== null && typeof data.error !== "string")
      || (data.id !== null && typeof data.id !== "string")) throw new Error("Ungültiger Installationsstatus");
  if (data.configured_fields !== undefined && (!Array.isArray(data.configured_fields) || !data.configured_fields.every(field => ["model_name", "tts_engine", "tts_model_path", "tts_voice", "whisper_model_path", "whisper_binary"].includes(field)))) throw new Error("Ungültige Konfigurationsfelder");
  if (data.cancellable !== undefined && typeof data.cancellable !== "boolean") throw new Error("Ungültiger Abbruchstatus");
  return data;
}

export function parseInstallOptions(value: unknown): InstallOptions {
  const data = value as InstallOptions;
  if (!data || !Array.isArray(data.whisper_models) || !data.whisper_models.every(x => typeof x === "string")
      || !Array.isArray(data.voices) || !data.voices.every(x => x && typeof x.id === "string" && typeof x.name === "string")) throw new Error("Ungültige Installationsauswahl");
  return data;
}
