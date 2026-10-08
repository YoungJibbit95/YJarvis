export type AcceleratorAdapter = {
  display_name: string;
  dedicated_video_memory_bytes: number | null;
  shared_system_memory_bytes: number | null;
  classification: "hardware" | "software" | "unknown";
};
export type AcceleratorProfile = {
  status: "available" | "unknown" | "unsupported";
  adapters: AcceleratorAdapter[];
};

function invalid(): never { throw new Error("Invalid accelerator profile"); }
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const data = value as Record<string, unknown>;
  if (Object.keys(data).length !== keys.length || keys.some((key) => !Object.prototype.hasOwnProperty.call(data, key))) return invalid();
  return data;
}
function memory(value: unknown): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) return invalid();
  return value;
}

export function parseAcceleratorProfile(value: unknown): AcceleratorProfile {
  const data = object(value, ["status", "adapters"]);
  if (data.status !== "available" && data.status !== "unknown" && data.status !== "unsupported") return invalid();
  if (!Array.isArray(data.adapters) || data.adapters.length > 64 || (data.status !== "available" && data.adapters.length !== 0)) return invalid();
  const adapters = data.adapters.map((value): AcceleratorAdapter => {
    const adapter = object(value, ["display_name", "dedicated_video_memory_bytes", "shared_system_memory_bytes", "classification"]);
    if (typeof adapter.display_name !== "string" || !adapter.display_name.trim() || [...adapter.display_name].length > 128) return invalid();
    if (adapter.classification !== "hardware" && adapter.classification !== "software" && adapter.classification !== "unknown") return invalid();
    return {
      display_name: adapter.display_name,
      dedicated_video_memory_bytes: memory(adapter.dedicated_video_memory_bytes),
      shared_system_memory_bytes: memory(adapter.shared_system_memory_bytes),
      classification: adapter.classification
    };
  });
  return { status: data.status, adapters };
}
