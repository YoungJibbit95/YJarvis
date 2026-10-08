export type ModelSource = { publisher: string; url: string; checked_on: string };
export type ModelLicense = { name: string | null; scope: "model" | "dataset"; source: ModelSource };
export type ModelCatalogEntry = {
  id: string;
  category: "chat" | "speech_to_text" | "text_to_speech";
  display_name: string;
  publisher: string;
  model_id: string;
  description: string;
  source: ModelSource;
  licenses: ModelLicense[];
  runtime: { backend: "ollama" | "whisper_cpp" | "piper"; model_id: string };
  acquisition: { mechanism: "ollama_library" | "hugging_face_files"; source: ModelSource; approximate_download_bytes: number | null };
  context_window_tokens: number | null;
  publisher_quality_label: string | null;
};

function invalid(): never { throw new Error("Invalid model catalog"); }
function record(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const data = value as Record<string, unknown>;
  if (Object.keys(data).length !== keys.length || keys.some((key) => !Object.prototype.hasOwnProperty.call(data, key))) return invalid();
  return data;
}
function text(value: unknown): string {
  if (typeof value !== "string" || !/^\S(?:[^\r\n]*\S)?$/.test(value)) return invalid();
  return value;
}
function choice<T extends string>(value: unknown, values: readonly T[]): T {
  if (typeof value !== "string" || !values.includes(value as T)) return invalid();
  return value as T;
}
function optionalText(value: unknown): string | null { return value === null ? null : text(value); }
function optionalCount(value: unknown): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value <= 0) return invalid();
  return value;
}
function source(value: unknown): ModelSource {
  const data = record(value, ["publisher", "url", "checked_on"]);
  const url = text(data.url);
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) return invalid();
  const checked = text(data.checked_on);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(checked) || new Date(checked).toISOString().slice(0, 10) !== checked) return invalid();
  return { publisher: text(data.publisher), url, checked_on: checked };
}
function entry(value: unknown): ModelCatalogEntry {
  const data = record(value, ["id", "category", "display_name", "publisher", "model_id", "description", "source", "licenses", "runtime", "acquisition", "context_window_tokens", "publisher_quality_label"]);
  const id = text(data.id);
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)) return invalid();
  const category = choice(data.category, ["chat", "speech_to_text", "text_to_speech"] as const);
  const runtime = record(data.runtime, ["backend", "model_id"]);
  const backend = choice(runtime.backend, ["ollama", "whisper_cpp", "piper"] as const);
  const acquisition = record(data.acquisition, ["mechanism", "source", "approximate_download_bytes"]);
  const mechanism = choice(acquisition.mechanism, ["ollama_library", "hugging_face_files"] as const);
  const acquisitionSource = source(acquisition.source);
  const expectedBackend = { chat: "ollama", speech_to_text: "whisper_cpp", text_to_speech: "piper" }[category];
  if (backend !== expectedBackend || mechanism !== (backend === "ollama" ? "ollama_library" : "hugging_face_files")) return invalid();
  if (new URL(acquisitionSource.url).hostname !== (mechanism === "ollama_library" ? "ollama.com" : "huggingface.co")) return invalid();
  if (!Array.isArray(data.licenses) || !data.licenses.length) return invalid();
  const licenses = data.licenses.map((item): ModelLicense => {
    const license = record(item, ["name", "scope", "source"]);
    return { name: optionalText(license.name), scope: choice(license.scope, ["model", "dataset"] as const), source: source(license.source) };
  });
  if (!licenses.some((license) => license.scope === "model") || new Set(licenses.map((license) => license.scope)).size !== licenses.length) return invalid();
  const context = optionalCount(data.context_window_tokens);
  if (category !== "chat" && context !== null) return invalid();
  return {
    id, category, display_name: text(data.display_name), publisher: text(data.publisher),
    model_id: text(data.model_id), description: text(data.description), source: source(data.source), licenses,
    runtime: { backend, model_id: text(runtime.model_id) },
    acquisition: { mechanism, source: acquisitionSource, approximate_download_bytes: optionalCount(acquisition.approximate_download_bytes) },
    context_window_tokens: context, publisher_quality_label: optionalText(data.publisher_quality_label)
  };
}

export function parseModelCatalog(value: unknown): ModelCatalogEntry[] {
  const data = record(value, ["entries"]);
  if (!Array.isArray(data.entries) || !data.entries.length) return invalid();
  const entries = data.entries.map(entry);
  if (new Set(entries.map((item) => item.id)).size !== entries.length
    || new Set(entries.map((item) => JSON.stringify([item.runtime.backend, item.runtime.model_id]))).size !== entries.length) return invalid();
  return entries;
}
