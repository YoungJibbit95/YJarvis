export type ComponentStatus = {
  status: "available" | "missing" | "unreachable" | "unknown" | "error";
  reason: string;
};

export type SetupStatus = {
  state: "needs_setup" | "ready" | "degraded" | "error";
  chat_model: ComponentStatus;
  stt: ComponentStatus;
  tts: ComponentStatus;
};

export type SetupCheck = {
  state: "checking" | SetupStatus["state"];
  backendReachable: boolean;
  report?: SetupStatus;
};

export function parseSetupStatus(value: unknown): SetupStatus {
  if (!value || typeof value !== "object") throw new Error("Invalid setup status");
  const data = value as SetupStatus;
  if (!["needs_setup", "ready", "degraded", "error"].includes(data.state)) {
    throw new Error("Invalid setup state");
  }
  for (const key of ["chat_model", "stt", "tts"] as const) {
    const component = data[key];
    if (!component || !["available", "missing", "unreachable", "unknown", "error"].includes(component.status)
      || typeof component.reason !== "string") throw new Error("Invalid setup component");
  }
  const expected = ["unknown", "error"].includes(data.chat_model.status) ? "error"
    : data.chat_model.status !== "available" ? "needs_setup"
    : data.stt.status !== "available" || data.tts.status !== "available" ? "degraded" : "ready";
  if (data.state !== expected) throw new Error("Inconsistent setup status");
  return data;
}
