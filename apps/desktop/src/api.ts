import type { Approval, JarvisSettings, SmartHomeEntity } from "@jarvis/shared-types";
import { recordingFileName } from "./voice/voiceReliability";
import { parseSetupStatus, type SetupStatus } from "./setup/types";
import { parseModelCatalog, type ModelCatalogEntry } from "./setup/modelCatalog";
import { parseHardwareProfile, type HardwareProfile } from "./setup/hardwareProfile";
import { parseAcceleratorProfile, type AcceleratorProfile } from "./setup/acceleratorProfile";
import { parseInstallOptions, parseInstallState, type InstallSelection } from "./setup/installTypes";

const AGENT_HOST = import.meta.env.VITE_JARVIS_AGENT_HOST || "127.0.0.1";
const AGENT_PORT = import.meta.env.VITE_JARVIS_AGENT_PORT || "8787";
const API_BASE = `http://${AGENT_HOST}:${AGENT_PORT}`;
const WS_BASE = `ws://${AGENT_HOST}:${AGENT_PORT}`;

export async function setupInstallation(action: "status" | "start" | "cancel", selection?: InstallSelection, signal?: AbortSignal) {
  const response = await fetch(`${API_BASE}/v1/setup/install`, {
    method: action === "start" ? "POST" : action === "cancel" ? "DELETE" : "GET",
    ...(selection ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(selection) } : {}), signal
  });
  if (!response.ok) throw new Error(await readErrorDetails(response, "Einrichtung nicht erreichbar"));
  return parseInstallState(await response.json());
}

export async function fetchInstallOptions(signal: AbortSignal) {
  const response = await fetch(`${API_BASE}/v1/setup/install/options`, { signal });
  if (!response.ok) throw new Error(await readErrorDetails(response, "Modellauswahl nicht erreichbar"));
  return parseInstallOptions(await response.json());
}

export type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

function compactErrorText(text: string, limit = 260): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "Unbekannter Fehler.";
  }
  if (normalized.length <= limit) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, limit - 3))}...`;
}

async function readErrorDetails(response: Response, fallback: string): Promise<string> {
  let raw = "";
  try {
    raw = await response.text();
  } catch {
    return fallback;
  }

  if (!raw) {
    return fallback;
  }

  try {
    const parsed = JSON.parse(raw) as { detail?: unknown; message?: unknown };
    const detail = typeof parsed.detail === "string" ? parsed.detail : null;
    const message = typeof parsed.message === "string" ? parsed.message : null;

    if (detail) {
      return compactErrorText(detail);
    }
    if (message) {
      return compactErrorText(message);
    }
  } catch {
    return compactErrorText(raw);
  }

  return compactErrorText(raw);
}

function sleep(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export async function waitForBackend(maxWaitMs = 30_000, signal?: AbortSignal): Promise<void> {
  const deadline = Date.now() + maxWaitMs;
  let lastError = "unbekannter Fehler";

  while (Date.now() < deadline) {
    signal?.throwIfAborted();
    try {
      const response = await fetch(`${API_BASE}/health`, { cache: "no-store", signal });
      if (response.ok) {
        return;
      }
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      signal?.throwIfAborted();
      lastError = (error as Error).message;
    }

    await sleep(350);
  }

  throw new Error(`Backend nicht erreichbar (${lastError}). Bitte Agent-Start prüfen.`);
}

export async function fetchSetupStatus(signal: AbortSignal): Promise<SetupStatus> {
  const response = await fetch(`${API_BASE}/v1/setup/status`, { cache: "no-store", signal });
  if (!response.ok) throw new Error("Setup inspection failed");
  return parseSetupStatus(await response.json());
}

export async function fetchModelCatalog(signal: AbortSignal): Promise<ModelCatalogEntry[]> {
  const response = await fetch(`${API_BASE}/v1/setup/models`, { cache: "no-store", signal });
  if (!response.ok) throw new Error("Model catalog unavailable");
  return parseModelCatalog(await response.json());
}

export async function fetchHardwareProfile(signal: AbortSignal): Promise<HardwareProfile> {
  const response = await fetch(`${API_BASE}/v1/setup/hardware`, { cache: "no-store", signal });
  if (!response.ok) throw new Error("Hardware profile unavailable");
  return parseHardwareProfile(await response.json());
}

export async function fetchAcceleratorProfile(signal: AbortSignal): Promise<AcceleratorProfile> {
  const response = await fetch(`${API_BASE}/v1/setup/accelerators`, { cache: "no-store", signal });
  if (!response.ok) throw new Error("Accelerator profile unavailable");
  return parseAcceleratorProfile(await response.json());
}

export async function createSession(): Promise<{ session_id: string }> {
  const response = await fetch(`${API_BASE}/v1/sessions`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Session konnte nicht erstellt werden (${response.status}).`);
  }
  return response.json();
}

export async function fetchMessages(sessionId: string): Promise<ChatMessage[]> {
  const response = await fetch(`${API_BASE}/v1/sessions/${sessionId}/messages`);
  if (!response.ok) {
    throw new Error(`Nachrichten konnten nicht geladen werden (${response.status}).`);
  }
  return response.json();
}

export class ChatSubmissionError extends Error {
  constructor(message: string, readonly outcome: "rejected" | "unknown") {
    super(message);
    this.name = "ChatSubmissionError";
  }
}

export async function sendChat(sessionId: string, message: string): Promise<{ run_id: string }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
      // A stalled ACK is uncertain, not permission to issue another agent run.
      signal: AbortSignal.timeout(60_000)
    });
  } catch (error) {
    // The backend may have committed a run before an HTTP acknowledgement was lost.
    throw new ChatSubmissionError("Verbindung abgebrochen: Annahme durch Agent unklar. " +
      (error instanceof Error ? error.message : String(error)), "unknown");
  }
  if (!response.ok) {
    const details = await readErrorDetails(response, `HTTP ${response.status}`);
    // 5xx/408/429 might follow a committed run when a gateway drops the ACK.
    const outcome = response.status >= 500 || [408, 429].includes(response.status) ? "unknown" : "rejected";
    throw new ChatSubmissionError(`Chat ${outcome === "unknown" ? "nicht bestätigt" : "wurde abgelehnt"}: ${details}`, outcome);
  }
  try {
    const result: unknown = await response.json();
    if (!result || typeof result !== "object" || typeof (result as { run_id?: unknown }).run_id !== "string") {
      throw new Error("Ungültige Chat-Antwort");
    }
    return result as { run_id: string };
  } catch (error) {
    throw new ChatSubmissionError("Agent-Antwort nicht lesbar: Annahme möglicherweise erfolgt. " +
      (error instanceof Error ? error.message : String(error)), "unknown");
  }
}

export async function fetchApprovals(): Promise<Approval[]> {
  const response = await fetch(`${API_BASE}/v1/approvals/pending`);
  if (!response.ok) {
    throw new Error(`Approvals konnten nicht geladen werden (${response.status}).`);
  }
  return response.json();
}

export async function decideApproval(approvalId: string, decision: "approve" | "deny") {
  const response = await fetch(`${API_BASE}/v1/approvals/${approvalId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ decision })
  });
  if (!response.ok) {
    const details = await readErrorDetails(response, `HTTP ${response.status}`);
    throw new Error(`Approval konnte nicht entschieden werden: ${details}`);
  }
  return response.json();
}

export async function fetchSettings(): Promise<JarvisSettings> {
  const response = await fetch(`${API_BASE}/v1/settings`);
  if (!response.ok) {
    throw new Error(`Settings konnten nicht geladen werden (${response.status}).`);
  }
  return response.json();
}

export async function saveSettings(payload: Partial<JarvisSettings>): Promise<JarvisSettings> {
  const response = await fetch(`${API_BASE}/v1/settings`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const details = await readErrorDetails(response, `HTTP ${response.status}`);
    throw new Error(`Settings konnten nicht gespeichert werden: ${details}`);
  }
  return response.json();
}

export async function transcribe(blob: Blob): Promise<{ text: string; language: string; latency_ms: number }> {
  const formData = new FormData();
  formData.append("file", blob, recordingFileName(blob.type));

  const response = await fetch(`${API_BASE}/v1/audio/transcribe`, {
    method: "POST",
    body: formData,
    signal: AbortSignal.timeout(660_000)
  });

  if (!response.ok) {
    const details = await readErrorDetails(response, `HTTP ${response.status}`);
    throw new Error(`Transkription fehlgeschlagen: ${details}`);
  }

  return response.json();
}

export async function fetchAudioVoices(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/v1/audio/voices`);
  if (!response.ok) {
    const details = await readErrorDetails(response, `HTTP ${response.status}`);
    throw new Error(`Stimmen konnten nicht geladen werden: ${details}`);
  }
  return response.json();
}

export async function speak(text: string): Promise<{ ok: boolean; duration_ms: number }> {
  const response = await fetch(`${API_BASE}/v1/audio/speak`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ text })
  });

  if (!response.ok) {
    const details = await readErrorDetails(response, `HTTP ${response.status}`);
    throw new Error(`Sprachausgabe fehlgeschlagen: ${details}`);
  }

  return response.json();
}

export async function fetchSmartHomeEntities(): Promise<SmartHomeEntity[]> {
  const response = await fetch(`${API_BASE}/v1/smarthome/entities`);
  if (!response.ok) {
    throw new Error(`Smart-Home Entities konnten nicht geladen werden (${response.status}).`);
  }
  return response.json();
}

export async function callSmartHomeService(entityId: string, service: string): Promise<SmartHomeEntity> {
  const response = await fetch(`${API_BASE}/v1/smarthome/call`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ entity_id: entityId, service })
  });

  if (!response.ok) {
    const details = await readErrorDetails(response, `HTTP ${response.status}`);
    throw new Error(`Smart-Home Service fehlgeschlagen: ${details}`);
  }

  return response.json();
}

export function wsUrl(sessionId: string) {
  return `${WS_BASE}/v1/ws/${sessionId}`;
}
