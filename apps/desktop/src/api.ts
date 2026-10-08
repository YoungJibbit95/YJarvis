import type { Approval, JarvisSettings, SmartHomeEntity } from "@jarvis/shared-types";
import { parseSetupStatus, type SetupStatus } from "./setup/types";

const AGENT_HOST = import.meta.env.VITE_JARVIS_AGENT_HOST || "127.0.0.1";
const AGENT_PORT = import.meta.env.VITE_JARVIS_AGENT_PORT || "8787";
const API_BASE = `http://${AGENT_HOST}:${AGENT_PORT}`;
const WS_BASE = `ws://${AGENT_HOST}:${AGENT_PORT}`;

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

export async function sendChat(sessionId: string, message: string): Promise<{ run_id: string }> {
  const response = await fetch(`${API_BASE}/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ session_id: sessionId, message })
  });
  if (!response.ok) {
    const details = await readErrorDetails(response, `HTTP ${response.status}`);
    throw new Error(`Chat konnte nicht gesendet werden: ${details}`);
  }
  return response.json();
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
  formData.append("file", blob, "recording.webm");

  const response = await fetch(`${API_BASE}/v1/audio/transcribe`, {
    method: "POST",
    body: formData
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
