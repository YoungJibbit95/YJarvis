import type { Dispatch, SetStateAction } from "react";
import type { JarvisSettings, LearningOverview, PerfOverview } from "@jarvis/shared-types";

type UiThemePreset = {
  label: string;
  accent: string;
  secondary: string;
  glow: number;
};

type SettingsPanelProps = {
  settings: JarvisSettings;
  settingsDraft: JarvisSettings;
  setSettingsDraft: Dispatch<SetStateAction<JarvisSettings>>;
  allowlistInput: string;
  setAllowlistInput: (value: string) => void;
  sayVoices: string[];
  learningOverview: LearningOverview | null;
  learningLoading: boolean;
  perfOverview: PerfOverview | null;
  perfLoading: boolean;
  uiThemePresets: UiThemePreset[];
  defaultSettings: JarvisSettings;
  normalizeHexColor: (value: string, fallback: string) => string;
  clamp: (value: number, min: number, max: number) => number;
  formatPercent: (value: number) => string;
  formatLatency: (value: number) => string;
  onRefreshVoices: () => void;
  onAddAllowlistPath: () => void;
  onRemoveAllowlistPath: (path: string) => void;
  onRefreshLearning: () => void;
  onRefreshPerf: () => void;
  onSaveSettings: () => void;
};

export default function SettingsPanel({
  settings,
  settingsDraft,
  setSettingsDraft,
  allowlistInput,
  setAllowlistInput,
  sayVoices,
  learningOverview,
  learningLoading,
  perfOverview,
  perfLoading,
  uiThemePresets,
  defaultSettings,
  normalizeHexColor,
  clamp,
  formatPercent,
  formatLatency,
  onRefreshVoices,
  onAddAllowlistPath,
  onRemoveAllowlistPath,
  onRefreshLearning,
  onRefreshPerf,
  onSaveSettings
}: SettingsPanelProps) {
  const isSayEngine = settingsDraft.tts_engine.trim().toLowerCase() === "say";
  const currentVoiceMissingFromList =
    settingsDraft.tts_voice.trim().length > 0 && !sayVoices.includes(settingsDraft.tts_voice);
  const topToolStats = learningOverview?.tool_stats.slice(0, 8) || [];
  const learnedCommands = learningOverview?.learned_commands.slice(0, 10) || [];
  const glowPreview = clamp(Number(settingsDraft.ui_glow_strength) || 0, 0.6, 2.2).toFixed(2);
  const panelOpacityPreview = clamp(Number(settingsDraft.ui_panel_opacity) || 0, 0.45, 0.9).toFixed(2);
  const backgroundDimPreview = clamp(Number(settingsDraft.ui_background_dim) || 0, 0.15, 0.78).toFixed(2);
  const chatOrbOpacityPreview = clamp(Number(settingsDraft.ui_chat_orb_opacity) || 0, 0.08, 0.7).toFixed(2);
  const motionIntensityPreview = clamp(Number(settingsDraft.ui_motion_intensity) || 0, 0.6, 1.8).toFixed(2);
  const runTotalP95 = perfOverview?.metrics?.run_total_ms?.p95 ?? 0;
  const ttftP50 = perfOverview?.metrics?.ttft_ms?.p50 ?? 0;

  return (
    <section className="grid h-full min-h-0 grid-cols-1 gap-4 lg:grid-cols-[1.18fr_0.82fr]">
      <div className="glass-panel min-h-0 overflow-hidden p-4">
        <header className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-xs uppercase tracking-[0.2em] text-jarvis-cyan">Runtime Settings</h2>
          <span className="text-[10px] text-white/50">Local only</span>
        </header>

        <div className="custom-scrollbar grid h-full min-h-0 gap-3 overflow-auto pr-1 sm:grid-cols-2">
          <label className="text-[11px] text-white/65">
            Modell
            <input
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
              value={settingsDraft.model_name}
              onChange={(event) => setSettingsDraft((previous) => ({ ...previous, model_name: event.target.value }))}
            />
          </label>

          <label className="text-[11px] text-white/65">
            Sprache
            <input
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
              value={settingsDraft.language}
              onChange={(event) => setSettingsDraft((previous) => ({ ...previous, language: event.target.value }))}
            />
          </label>

          <label className="text-[11px] text-white/65 sm:col-span-2">
            Ollama URL
            <input
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
              value={settingsDraft.ollama_base_url}
              onChange={(event) =>
                setSettingsDraft((previous) => ({ ...previous, ollama_base_url: event.target.value }))
              }
            />
          </label>

          <label className="text-[11px] text-white/65">
            TTS Engine
            <input
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
              value={settingsDraft.tts_engine}
              onChange={(event) => setSettingsDraft((previous) => ({ ...previous, tts_engine: event.target.value }))}
            />
          </label>

          <label className="text-[11px] text-white/65">
            Piper Modellpfad
            <input
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
              value={settingsDraft.tts_model_path}
              onChange={(event) =>
                setSettingsDraft((previous) => ({ ...previous, tts_model_path: event.target.value }))
              }
            />
          </label>

          <label className="text-[11px] text-white/65 sm:col-span-2">
            TTS Voice
            {isSayEngine ? (
              <div className="mt-1 flex gap-2">
                <select
                  className="w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
                  value={settingsDraft.tts_voice}
                  onChange={(event) => setSettingsDraft((previous) => ({ ...previous, tts_voice: event.target.value }))}
                >
                  {currentVoiceMissingFromList ? (
                    <option value={settingsDraft.tts_voice}>{settingsDraft.tts_voice} (aktuell)</option>
                  ) : null}
                  {sayVoices.map((voice) => (
                    <option key={voice} value={voice}>
                      {voice}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs text-white/80 transition hover:border-jarvis-cyan/35"
                  onClick={onRefreshVoices}
                >
                  Neu laden
                </button>
              </div>
            ) : (
              <input
                className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
                value={settingsDraft.tts_voice}
                onChange={(event) => setSettingsDraft((previous) => ({ ...previous, tts_voice: event.target.value }))}
              />
            )}
          </label>

          <label className="text-[11px] text-white/65">
            say Rate (WPM)
            <input
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
              type="number"
              min={80}
              max={420}
              value={settingsDraft.say_rate_wpm}
              onChange={(event) =>
                setSettingsDraft((previous) => ({
                  ...previous,
                  say_rate_wpm: Number.isFinite(Number(event.target.value))
                    ? Number(event.target.value)
                    : previous.say_rate_wpm
                }))
              }
            />
          </label>

          <label className="text-[11px] text-white/65">
            Sir Aussprache (TTS)
            <input
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
              value={settingsDraft.tts_sir_pronunciation}
              onChange={(event) =>
                setSettingsDraft((previous) => ({ ...previous, tts_sir_pronunciation: event.target.value }))
              }
              placeholder="Sör"
            />
          </label>

          <label className="text-[11px] text-white/65 sm:col-span-2">
            Whisper Modellpfad
            <input
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
              value={settingsDraft.whisper_model_path}
              onChange={(event) =>
                setSettingsDraft((previous) => ({ ...previous, whisper_model_path: event.target.value }))
              }
            />
          </label>

          <label className="text-[11px] text-white/65 sm:col-span-2">
            Whisper Binary
            <input
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
              value={settingsDraft.whisper_binary}
              onChange={(event) => setSettingsDraft((previous) => ({ ...previous, whisper_binary: event.target.value }))}
            />
          </label>

          <article className="rounded-xl border border-white/15 bg-white/5 p-3 sm:col-span-2">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-[11px] uppercase tracking-[0.14em] text-jarvis-cyan">UI Customization</h3>
              <span className="text-[10px] text-white/45">Live Preview Enabled</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-[11px] text-white/65">
                Accent Color
                <div className="mt-1 flex gap-2">
                  <input
                    className="h-9 w-11 rounded-md border border-white/15 bg-black/40"
                    type="color"
                    value={normalizeHexColor(settingsDraft.ui_accent_color, defaultSettings.ui_accent_color)}
                    onChange={(event) =>
                      setSettingsDraft((previous) => ({ ...previous, ui_accent_color: event.target.value }))
                    }
                  />
                  <input
                    className="w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
                    value={settingsDraft.ui_accent_color}
                    onChange={(event) =>
                      setSettingsDraft((previous) => ({ ...previous, ui_accent_color: event.target.value }))
                    }
                  />
                </div>
              </label>

              <label className="text-[11px] text-white/65">
                Secondary Color
                <div className="mt-1 flex gap-2">
                  <input
                    className="h-9 w-11 rounded-md border border-white/15 bg-black/40"
                    type="color"
                    value={normalizeHexColor(settingsDraft.ui_secondary_color, defaultSettings.ui_secondary_color)}
                    onChange={(event) =>
                      setSettingsDraft((previous) => ({ ...previous, ui_secondary_color: event.target.value }))
                    }
                  />
                  <input
                    className="w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
                    value={settingsDraft.ui_secondary_color}
                    onChange={(event) =>
                      setSettingsDraft((previous) => ({ ...previous, ui_secondary_color: event.target.value }))
                    }
                  />
                </div>
              </label>

              <label className="text-[11px] text-white/65 sm:col-span-2">
                Glow Strength ({glowPreview}x)
                <input
                  className="mt-2 w-full"
                  type="range"
                  min={0.6}
                  max={2.2}
                  step={0.05}
                  value={clamp(Number(settingsDraft.ui_glow_strength) || defaultSettings.ui_glow_strength, 0.6, 2.2)}
                  onChange={(event) =>
                    setSettingsDraft((previous) => ({
                      ...previous,
                      ui_glow_strength: Number(event.target.value)
                    }))
                  }
                />
              </label>

              <label className="text-[11px] text-white/65">
                Panel Opacity ({panelOpacityPreview})
                <input
                  className="mt-2 w-full"
                  type="range"
                  min={0.45}
                  max={0.9}
                  step={0.01}
                  value={clamp(Number(settingsDraft.ui_panel_opacity) || defaultSettings.ui_panel_opacity, 0.45, 0.9)}
                  onChange={(event) =>
                    setSettingsDraft((previous) => ({
                      ...previous,
                      ui_panel_opacity: Number(event.target.value)
                    }))
                  }
                />
              </label>

              <label className="text-[11px] text-white/65">
                Background Dim ({backgroundDimPreview})
                <input
                  className="mt-2 w-full"
                  type="range"
                  min={0.15}
                  max={0.78}
                  step={0.01}
                  value={clamp(Number(settingsDraft.ui_background_dim) || defaultSettings.ui_background_dim, 0.15, 0.78)}
                  onChange={(event) =>
                    setSettingsDraft((previous) => ({
                      ...previous,
                      ui_background_dim: Number(event.target.value)
                    }))
                  }
                />
              </label>

              <label className="text-[11px] text-white/65">
                Chat Orb Opacity ({chatOrbOpacityPreview})
                <input
                  className="mt-2 w-full"
                  type="range"
                  min={0.08}
                  max={0.7}
                  step={0.01}
                  value={clamp(Number(settingsDraft.ui_chat_orb_opacity) || defaultSettings.ui_chat_orb_opacity, 0.08, 0.7)}
                  onChange={(event) =>
                    setSettingsDraft((previous) => ({
                      ...previous,
                      ui_chat_orb_opacity: Number(event.target.value)
                    }))
                  }
                />
              </label>

              <label className="text-[11px] text-white/65">
                Motion Intensity ({motionIntensityPreview}x)
                <input
                  className="mt-2 w-full"
                  type="range"
                  min={0.6}
                  max={1.8}
                  step={0.05}
                  value={clamp(Number(settingsDraft.ui_motion_intensity) || defaultSettings.ui_motion_intensity, 0.6, 1.8)}
                  onChange={(event) =>
                    setSettingsDraft((previous) => ({
                      ...previous,
                      ui_motion_intensity: Number(event.target.value)
                    }))
                  }
                />
              </label>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {uiThemePresets.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-[10px] uppercase tracking-[0.12em] text-white/75 transition hover:border-jarvis-cyan/35"
                  onClick={() =>
                    setSettingsDraft((previous) => ({
                      ...previous,
                      ui_accent_color: preset.accent,
                      ui_secondary_color: preset.secondary,
                      ui_glow_strength: preset.glow
                    }))
                  }
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </article>
        </div>
      </div>

      <aside className="glass-panel min-h-0 overflow-hidden p-4">
        <header className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-xs uppercase tracking-[0.2em] text-jarvis-cyan">Safety + Learning</h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/80 transition hover:border-jarvis-cyan/35"
              onClick={onRefreshPerf}
              disabled={perfLoading}
            >
              {perfLoading ? "Perf..." : "Perf"}
            </button>
            <button
              type="button"
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/80 transition hover:border-jarvis-cyan/35"
              onClick={onRefreshLearning}
              disabled={learningLoading}
            >
              {learningLoading ? "Lädt..." : "Refresh"}
            </button>
          </div>
        </header>

        <div className="custom-scrollbar h-full min-h-0 space-y-3 overflow-auto pr-1">
          <article className="rounded-xl border border-white/15 bg-white/5 p-3">
            <h3 className="mb-2 text-[11px] uppercase tracking-[0.14em] text-jarvis-cyan">Performance Health</h3>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-md border border-white/10 bg-black/35 p-2">
                <span className="text-[10px] text-white/55">Runs</span>
                <strong className="mt-1 block text-sm text-jarvis-cyan">{perfOverview?.sample_size ?? 0}</strong>
              </div>
              <div className="rounded-md border border-white/10 bg-black/35 p-2">
                <span className="text-[10px] text-white/55">TTFT P50</span>
                <strong className="mt-1 block text-sm text-jarvis-cyan">{formatLatency(ttftP50)}</strong>
              </div>
              <div className="rounded-md border border-white/10 bg-black/35 p-2">
                <span className="text-[10px] text-white/55">Run P95</span>
                <strong className="mt-1 block text-sm text-jarvis-cyan">{formatLatency(runTotalP95)}</strong>
              </div>
              <div className="rounded-md border border-white/10 bg-black/35 p-2">
                <span className="text-[10px] text-white/55">Tool P95</span>
                <strong className="mt-1 block text-sm text-jarvis-cyan">
                  {formatLatency(perfOverview?.metrics?.tool_exec_ms?.p95 ?? 0)}
                </strong>
              </div>
            </div>
          </article>

          <article className="rounded-xl border border-white/15 bg-white/5 p-3">
            <h3 className="mb-2 text-[11px] uppercase tracking-[0.14em] text-jarvis-cyan">Allowed Paths</h3>
            <div className="mb-2 flex gap-2">
              <input
                className="w-full rounded-lg border border-white/15 bg-black/45 px-3 py-2 text-xs text-white outline-none focus:border-jarvis-cyan/50"
                value={allowlistInput}
                onChange={(event) => setAllowlistInput(event.target.value)}
                placeholder="/Users/.../Dokumente"
              />
              <button
                type="button"
                className="rounded-lg border border-jarvis-cyan/35 bg-jarvis-cyan/10 px-3 py-2 text-xs text-jarvis-cyan transition hover:bg-jarvis-cyan/20"
                onClick={onAddAllowlistPath}
              >
                Add
              </button>
            </div>
            <ul className="space-y-2">
              {settingsDraft.allowed_paths.map((path) => (
                <li key={path} className="flex items-center justify-between gap-2 rounded-md border border-white/10 bg-black/35 p-2">
                  <code className="truncate text-[10px] text-white/80">{path}</code>
                  <button
                    type="button"
                    className="rounded-md border border-white/15 bg-white/5 px-2 py-1 text-[10px] text-white/75 transition hover:border-jarvis-cyan/35"
                    onClick={() => onRemoveAllowlistPath(path)}
                  >
                    Remove
                  </button>
                </li>
              ))}
              {!settingsDraft.allowed_paths.length ? (
                <li className="text-xs text-white/55">Keine Allowlist-Pfade gesetzt.</li>
              ) : null}
            </ul>
          </article>

          <article className="rounded-xl border border-white/15 bg-white/5 p-3">
            <h3 className="mb-2 text-[11px] uppercase tracking-[0.14em] text-jarvis-cyan">Skill Evaluation</h3>
            <div className="mb-3 grid grid-cols-2 gap-2">
              <div className="rounded-md border border-white/10 bg-black/35 p-2">
                <span className="text-[10px] text-white/55">Tool Runs</span>
                <strong className="mt-1 block text-sm text-jarvis-cyan">{learningOverview?.summary.total_runs ?? 0}</strong>
              </div>
              <div className="rounded-md border border-white/10 bg-black/35 p-2">
                <span className="text-[10px] text-white/55">Success</span>
                <strong className="mt-1 block text-sm text-jarvis-cyan">{formatPercent(learningOverview?.summary.success_rate ?? 0)}</strong>
              </div>
              <div className="rounded-md border border-white/10 bg-black/35 p-2">
                <span className="text-[10px] text-white/55">Avg Latency</span>
                <strong className="mt-1 block text-sm text-jarvis-cyan">{formatLatency(learningOverview?.summary.average_latency_ms ?? 0)}</strong>
              </div>
              <div className="rounded-md border border-white/10 bg-black/35 p-2">
                <span className="text-[10px] text-white/55">Commands</span>
                <strong className="mt-1 block text-sm text-jarvis-cyan">{learningOverview?.learned_commands.length ?? 0}</strong>
              </div>
            </div>

            <div className="grid gap-2">
              <section>
                <h4 className="mb-1 text-[10px] uppercase tracking-[0.12em] text-white/55">Top Tools</h4>
                <ul className="space-y-1.5">
                  {topToolStats.map((tool) => (
                    <li key={tool.tool_name} className="rounded-md border border-white/10 bg-black/35 p-2 text-[11px]">
                      <div className="flex items-center justify-between text-white/80">
                        <strong>{tool.tool_name}</strong>
                        <span>{tool.total_runs} runs</span>
                      </div>
                      <p className="mt-0.5 text-white/55">{formatPercent(tool.success_rate)} · {formatLatency(tool.average_latency_ms)}</p>
                    </li>
                  ))}
                  {!topToolStats.length ? <li className="text-xs text-white/55">Noch keine Tool-Lernwerte.</li> : null}
                </ul>
              </section>

              <section>
                <h4 className="mb-1 text-[10px] uppercase tracking-[0.12em] text-white/55">Learned Commands</h4>
                <ul className="space-y-1.5">
                  {learnedCommands.map((command) => (
                    <li key={command.trigger} className="rounded-md border border-white/10 bg-black/35 p-2 text-[11px]">
                      <div className="flex items-center justify-between text-white/80">
                        <strong>{command.trigger}</strong>
                        <span>{command.tool_name}</span>
                      </div>
                      <p className="mt-0.5 text-white/55">
                        Uses {command.usage_count} · OK {command.success_count} · Fail {command.failure_count}
                      </p>
                    </li>
                  ))}
                  {!learnedCommands.length ? <li className="text-xs text-white/55">Keine gelernten Trigger gespeichert.</li> : null}
                </ul>
              </section>
            </div>
          </article>
        </div>

        <footer className="mt-3 flex items-center justify-between border-t border-white/10 pt-3">
          <button
            type="button"
            className="rounded-full border border-jarvis-cyan/35 bg-jarvis-cyan/10 px-4 py-1.5 text-xs font-semibold text-jarvis-cyan transition hover:bg-jarvis-cyan/20"
            onClick={onSaveSettings}
          >
            Speichern
          </button>
          <span className="text-[10px] text-white/55">Aktiv: {settings.model_name}</span>
        </footer>
      </aside>
    </section>
  );
}
