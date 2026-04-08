from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _resolve_project_root() -> Path:
  env_root = os.environ.get("JARVIS_PROJECT_ROOT")
  if env_root:
    return Path(env_root).expanduser().resolve()
  return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class AppConfig:
  project_root: Path
  runtime_dir: Path
  db_path: Path
  audio_tmp_dir: Path
  tts_tmp_dir: Path
  default_whisper_model: Path
  profile_path: Path
  host: str
  port: int


def load_config() -> AppConfig:
  project_root = _resolve_project_root()
  runtime_dir = Path(
    os.environ.get("JARVIS_RUNTIME_DIR", str(project_root / "runtime"))
  ).expanduser().resolve()
  audio_tmp_dir = runtime_dir / "audio"
  tts_tmp_dir = runtime_dir / "tts"

  db_path = Path(
    os.environ.get("JARVIS_DB_PATH", str(runtime_dir / "jarvis.db"))
  ).expanduser().resolve()

  default_whisper_model = Path(
    os.environ.get(
      "WHISPER_MODEL",
      str(runtime_dir / "models" / "ggml-small.bin")
    )
  ).expanduser().resolve()

  profile_path = Path(
    os.environ.get(
      "JARVIS_PROFILE_PATH",
      str(runtime_dir / "jarvis_profile.json")
    )
  ).expanduser().resolve()

  return AppConfig(
    project_root=project_root,
    runtime_dir=runtime_dir,
    db_path=db_path,
    audio_tmp_dir=audio_tmp_dir,
    tts_tmp_dir=tts_tmp_dir,
    default_whisper_model=default_whisper_model,
    profile_path=profile_path,
    host=os.environ.get("JARVIS_AGENT_HOST", "127.0.0.1"),
    port=int(os.environ.get("JARVIS_AGENT_PORT", "8787"))
  )


def ensure_runtime_dirs(config: AppConfig) -> None:
  config.runtime_dir.mkdir(parents=True, exist_ok=True)
  config.audio_tmp_dir.mkdir(parents=True, exist_ok=True)
  config.tts_tmp_dir.mkdir(parents=True, exist_ok=True)
  config.default_whisper_model.parent.mkdir(parents=True, exist_ok=True)
  config.profile_path.parent.mkdir(parents=True, exist_ok=True)
