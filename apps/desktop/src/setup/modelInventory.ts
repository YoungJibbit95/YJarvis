export type InstalledChatModel = {
  name: string; digest: string; size_bytes: number | null;
  active: boolean; installed: true; verified_inference: false;
};
export type InstalledFileModel = {
  name: string; path: string; active: boolean; installed: true;
  verified_inference?: false; paired_config?: true; verified_playback?: false;
};
export type ModelInventory = {
  ollama: { status: "online" | "offline" | "error"; models: InstalledChatModel[]; active_model: string; error: string | null };
  whisper: { models: InstalledFileModel[]; binary_available: boolean; ffmpeg_available: boolean; active_path: string; note: string };
  tts: { piper_voices: InstalledFileModel[]; piper_runtime_available: boolean; say_supported: boolean; active_engine: string; active_path: string; note: string };
};

function validRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

export function parseModelInventory(value: unknown): ModelInventory {
  if (!validRecord(value) || !validRecord(value.ollama) || !validRecord(value.whisper) || !validRecord(value.tts)) {
    throw new Error("Ungültiges Geräte- und Modellinventar");
  }
  const ollama = value.ollama, whisper = value.whisper, tts = value.tts;
  if (!["online", "offline", "error"].includes(String(ollama.status)) ||
    !Array.isArray(ollama.models) || !Array.isArray(whisper.models) || !Array.isArray(tts.piper_voices) ||
    typeof ollama.active_model !== "string" ||
    !(ollama.error === null || typeof ollama.error === "string") ||
    typeof whisper.binary_available !== "boolean" || typeof whisper.ffmpeg_available !== "boolean" ||
    typeof whisper.active_path !== "string" || typeof tts.say_supported !== "boolean" ||
    typeof tts.piper_runtime_available !== "boolean" || typeof tts.active_engine !== "string" ||
    typeof tts.active_path !== "string") throw new Error("Unvollständiges Geräte- und Modellinventar");
  for (const item of ollama.models) {
    if (!validRecord(item) || typeof item.name !== "string" || typeof item.digest !== "string" ||
      !(item.size_bytes === null || (typeof item.size_bytes === "number" && item.size_bytes >= 0)) ||
      item.installed !== true || typeof item.active !== "boolean") {
      throw new Error("Ungültiger Ollama-Modellstatus");
    }
  }
  for (const item of [...whisper.models, ...tts.piper_voices]) {
    if (!validRecord(item) || typeof item.name !== "string" || typeof item.path !== "string" ||
      item.installed !== true || typeof item.active !== "boolean") {
      throw new Error("Ungültiger lokaler Modellstatus");
    }
  }
  return value as ModelInventory;
}
