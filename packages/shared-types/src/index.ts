export type RunState =
  | "received"
  | "thinking"
  | "approval_required"
  | "executing"
  | "done"
  | "error";

export type StreamEvent =
  | {
      event: "run_state";
      run_id: string;
      state: RunState;
      detail?: string;
      timestamp: string;
      data?: Record<string, unknown>;
    }
  | {
      event: "token";
      run_id: string;
      token: string;
      timestamp: string;
    }
  | {
      event: "message";
      run_id: string;
      role: "assistant";
      content: string;
      timestamp: string;
    };

export type Approval = {
  id: string;
  session_id: string;
  run_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  status: "pending" | "approved" | "denied";
  requested_at: string;
};

export type JarvisSettings = {
  model_name: string;
  language: string;
  ollama_base_url: string;
  tts_engine: string;
  tts_model_path: string;
  tts_voice: string;
  say_rate_wpm: number;
  tts_sir_pronunciation: string;
  whisper_model_path: string;
  whisper_binary: string;
  allowed_paths: string[];
};

export type SmartHomeEntity = {
  id: string;
  entity_type: string;
  name: string;
  state: string;
  attributes: Record<string, unknown>;
};
