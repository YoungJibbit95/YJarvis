export type HardwareProfile = {
  platform: "windows" | "macos" | "linux" | "unknown";
  architecture: "x86_64" | "arm64" | "other" | "unknown";
  logical_cpu_count: number | null;
  total_memory_bytes: number | null;
  available_storage_bytes: number | null;
  storage_path_scope: "app_runtime_directory";
};

function invalid(): never { throw new Error("Invalid hardware profile"); }
function choice<T extends string>(value: unknown, values: readonly T[]): T {
  if (typeof value !== "string" || !values.includes(value as T)) return invalid();
  return value as T;
}
function count(value: unknown, minimum: number): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum) return invalid();
  return value;
}

export function parseHardwareProfile(value: unknown): HardwareProfile {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const data = value as Record<string, unknown>;
  const keys = ["platform", "architecture", "logical_cpu_count", "total_memory_bytes", "available_storage_bytes", "storage_path_scope"];
  if (Object.keys(data).length !== keys.length || keys.some((key) => !Object.prototype.hasOwnProperty.call(data, key))) return invalid();
  return {
    platform: choice(data.platform, ["windows", "macos", "linux", "unknown"] as const),
    architecture: choice(data.architecture, ["x86_64", "arm64", "other", "unknown"] as const),
    logical_cpu_count: count(data.logical_cpu_count, 1),
    total_memory_bytes: count(data.total_memory_bytes, 1),
    available_storage_bytes: count(data.available_storage_bytes, 0),
    storage_path_scope: choice(data.storage_path_scope, ["app_runtime_directory"] as const)
  };
}
