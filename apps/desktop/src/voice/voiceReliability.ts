/** Pure, hardware-independent state for the existing MediaRecorder/Whisper/chat path. */
export const WAKE_COMMAND_WINDOW_MS = 8_000;

export type WakeDecision =
  | { kind: "wake" }
  | { kind: "command"; command: string }
  | { kind: "ignored" };

const WAKE_PREFIX = /^(?:(?:hey|hallo|ok|okay)\s+)?jarvis\b[\s,.:;\-]*(.*)$/i;

/** Compare capture timestamps, not the time Whisper finishes, to avoid false expiry. */
export class WakeCommandWindow {
  private validUntil = -1;

  constructor(private readonly windowMs = WAKE_COMMAND_WINDOW_MS) {}

  accept(transcript: string, speechStartedAt: number): WakeDecision {
    const text = transcript.trim();
    const match = WAKE_PREFIX.exec(text);
    if (match) {
      const command = match[1].trim();
      if (command) {
        this.validUntil = -1;
        return { kind: "command", command };
      }
      // Another isolated wakeword refreshes the window without submitting.
      this.validUntil = speechStartedAt + this.windowMs;
      return { kind: "wake" };
    }
    if (text && speechStartedAt <= this.validUntil && speechStartedAt >= this.validUntil - this.windowMs) {
      this.validUntil = -1;
      return { kind: "command", command: text };
    }
    if (speechStartedAt > this.validUntil) this.validUntil = -1;
    return { kind: "ignored" };
  }

  reset(): void {
    this.validUntil = -1;
  }
}

/** A fresh activation owns its wake permission and capture-order queue.
 * A stopped activation may finalize recorded audio, but never arms a new activation.
 */
export class VoiceActivation {
  readonly wake = new WakeCommandWindow();
  readonly segments = new OrderedSegmentProcessor();
  private nextSegment = 0;

  constructor(readonly generation: number) {}

  allocateSegment(): number {
    return ++this.nextSegment;
  }

  cancel(): void {
    this.wake.reset();
    this.segments.cancel();
  }
}

/** Each recorder receives an ID at creation. Completion can arrive in any order. */
export class OrderedSegmentProcessor {
  private next = 1;
  private tasks = new Map<number, () => Promise<void>>();
  private running = false;
  private cancelled = false;

  complete(id: number, task: () => Promise<void>): void {
    if (this.cancelled || id < this.next || this.tasks.has(id)) return;
    this.tasks.set(id, task);
    void this.drain();
  }

  skip(id: number): void {
    this.complete(id, async () => {});
  }

  cancel(): void {
    this.cancelled = true;
    this.tasks.clear();
  }

  private async drain(): Promise<void> {
    if (this.running) return;
    this.running = true;
    try {
      while (!this.cancelled) {
        const task = this.tasks.get(this.next);
        if (!task) break;
        this.tasks.delete(this.next);
        this.next += 1;
        try {
          await task();
        } catch {
          // Task callers report their own errors; one failure never blocks later IDs.
        }
      }
    } finally {
      this.running = false;
      if (!this.cancelled && this.tasks.has(this.next)) void this.drain();
    }
  }
}

export type VoiceSubmissionState = "ready" | "submitting" | "accepted" | "pending" | "failed" | "cancelled";
export type VoiceSubmission = {
  id: string;
  transcript: string;
  command: string;
  capturedAt: number;
  state: VoiceSubmissionState;
  attempts: number;
  runId?: string;
  error?: string;
};

/** Preserve terminal events that race ahead of the HTTP run_id acknowledgement.
 * Only bounded run IDs and terminal states are kept; no message or audio payload.
 */
export class TerminalRunHistory {
  private states = new Map<string, "done" | "error">();

  constructor(private readonly maxEntries = 64) {}

  remember(id: string, state: "done" | "error"): void {
    if (this.states.has(id)) this.states.delete(id);
    this.states.set(id, state);
    while (this.states.size > this.maxEntries) {
      const first = this.states.keys().next().value;
      if (first === undefined) break;
      this.states.delete(first);
    }
  }

  get(id: string): "done" | "error" | undefined {
    return this.states.get(id);
  }

  get size(): number {
    return this.states.size;
  }
}

/** Monotonic IDs remain distinct with frozen clocks and predictable randomness. */
export function nextLocalMessageId(previous: number, now: number): number {
  return Math.max(previous + 1, Math.floor(now));
}

/** No automatic re-attempt after an ambiguous HTTP failure. */
export class VoiceSubmissionQueue {
  private entries: VoiceSubmission[] = [];

  add(id: string, transcript: string, command: string, capturedAt: number): void {
    if (this.entries.some((entry) => entry.id === id)) return;
    this.entries.push({ id, transcript, command, capturedAt, state: "ready", attempts: 0 });
  }

  claimNext(): VoiceSubmission | null {
    const entry = this.entries.find((item) => item.state !== "accepted" && item.state !== "cancelled");
    if (!entry || entry.state !== "ready") return null;
    entry.state = "submitting";
    entry.attempts += 1;
    return { ...entry };
  }

  settle(id: string, state: "accepted" | "pending" | "failed", detail?: string): void {
    const entry = this.entries.find((item) => item.id === id);
    if (!entry || entry.state !== "submitting") return;
    entry.state = state;
    if (state === "accepted") entry.runId = detail;
    else entry.error = detail;
    // Only old, acknowledged entries may be pruned; unresolved inputs survive.
    const accepted = this.entries.filter((item) => item.state === "accepted");
    if (accepted.length > 12) {
      const excess = new Set(accepted.slice(0, accepted.length - 12).map((item) => item.id));
      this.entries = this.entries.filter((item) => !excess.has(item.id));
    }
  }

  retryByUser(id: string): boolean {
    const entry = this.entries.find((item) => item.id === id);
    if (!entry || (entry.state !== "pending" && entry.state !== "failed")) return false;
    entry.state = "ready";
    entry.error = undefined;
    return true;
  }

  discardByUser(id: string): boolean {
    const entry = this.entries.find((item) => item.id === id);
    if (!entry || !["ready", "pending", "failed"].includes(entry.state)) return false;
    entry.state = "cancelled";
    return true;
  }

  snapshot(): VoiceSubmission[] {
    return this.entries.filter((item) => item.state !== "cancelled").map((item) => ({ ...item }));
  }
}

/** Filename extension must reflect the actual MediaRecorder container. */
export function recordingFileName(mimeType: string): string {
  const kind = mimeType.toLowerCase().split(";")[0].trim();
  if (kind === "audio/mp4" || kind === "audio/x-m4a") return "recording.mp4";
  if (kind === "audio/wav" || kind === "audio/wave" || kind === "audio/x-wav") return "recording.wav";
  if (kind === "audio/ogg") return "recording.ogg";
  if (kind === "audio/webm") return "recording.webm";
  return "recording.bin";
}
