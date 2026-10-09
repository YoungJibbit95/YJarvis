from __future__ import annotations

import asyncio
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import AppConfig
from .native_tools import find_system_tool, find_whisper_binary

try:
    from piper import PiperVoice, SynthesisConfig
except Exception:
    PiperVoice = None
    SynthesisConfig = None


class AudioError(RuntimeError):
    pass


DEFAULT_AUDIO_KEEP_ENTRIES = int(os.environ.get("JARVIS_AUDIO_TMP_KEEP", "30"))
DEFAULT_TTS_KEEP_ENTRIES = int(os.environ.get("JARVIS_TTS_TMP_KEEP", "20"))
DEFAULT_TMP_MAX_AGE_SECONDS = int(os.environ.get("JARVIS_TMP_MAX_AGE_SECONDS", str(12 * 60 * 60)))
DEFAULT_WHISPER_BEAM_SIZE = int(os.environ.get("JARVIS_WHISPER_BEAM_SIZE", "4"))
DEFAULT_WHISPER_BEST_OF = int(os.environ.get("JARVIS_WHISPER_BEST_OF", "4"))
DEFAULT_WHISPER_NO_SPEECH_THOLD = float(os.environ.get("JARVIS_WHISPER_NO_SPEECH_THOLD", "0.70"))
DEFAULT_WHISPER_ENTROPY_THOLD = float(os.environ.get("JARVIS_WHISPER_ENTROPY_THOLD", "2.10"))
DEFAULT_WHISPER_LOGPROB_THOLD = float(os.environ.get("JARVIS_WHISPER_LOGPROB_THOLD", "-0.60"))
# Real CPU whisper.cpp inference can take minutes. Keep generous finite ceilings.
STT_FFMPEG_TIMEOUT_SECONDS = 120.0
STT_WHISPER_TIMEOUT_SECONDS = 480.0
DEFAULT_PIPER_LENGTH_SCALE = float(os.environ.get("JARVIS_PIPER_LENGTH_SCALE", "0.80"))
DEFAULT_PIPER_NOISE_SCALE = float(os.environ.get("JARVIS_PIPER_NOISE_SCALE", "0.80"))
DEFAULT_PIPER_NOISE_W_SCALE = float(os.environ.get("JARVIS_PIPER_NOISE_W_SCALE", "0.88"))
DEFAULT_PIPER_SENTENCE_SILENCE = float(os.environ.get("JARVIS_PIPER_SENTENCE_SILENCE", "0.03"))
DEFAULT_PIPER_VOLUME = float(os.environ.get("JARVIS_PIPER_VOLUME", "1.10"))
DEFAULT_SAY_RATE_WPM = int(os.environ.get("JARVIS_SAY_RATE_WPM", "220"))
DEFAULT_PIPER_USE_PYTHON_API = os.environ.get("JARVIS_PIPER_USE_PYTHON_API", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

WAKE_WORD = "Jarvis"
WAKE_WORD_ALIASES = (
    "jobs",
    "job",
    "job is",
    "jop is",
    "jar vis",
    "javis",
    "jarviss",
    "jarwis",
    "jarwies",
    "jarvies",
    "charvis",
    "service",
    "servis",
)
WAKE_WORD_PREFIXES = ("hey", "hallo", "hi", "ok", "okay")
WAKE_WORD_COMMAND_HINTS = (
    "bitte",
    "mach",
    "starte",
    "oeffne",
    "schalte",
    "zeige",
    "sag",
    "sage",
    "kannst",
    "kannst du",
    "spiele",
)

BAVARIAN_TEXT_NORMALIZATIONS: tuple[tuple[str, str], ...] = (
    (r"(?i)\bi bin\b", "ich bin"),
    (r"(?i)\bi hab\b", "ich hab"),
    (r"(?i)\bi habe\b", "ich habe"),
    (r"(?i)\bi brauch\b", "ich brauch"),
    (r"(?i)\bi moechte\b", "ich moechte"),
    (r"(?i)\bi m[oö]chte\b", "ich moechte"),
    (r"(?i)\bned\b", "nicht"),
    (r"(?i)\bnet\b", "nicht"),
    (r"(?i)\bkoa\b", "kein"),
    (r"(?i)\bkoan\b", "keinen"),
    (r"(?i)\bdes\b", "das"),
    (r"(?i)\bmei\b", "mein"),
)

COMMON_STT_MISHEAR_NORMALIZATIONS: tuple[tuple[str, str], ...] = (
    # Frequent English-like mishearing for "danke dir Jarvis".
    (r"(?i)^\s*don(?:'?t)?\s+get\s+your\s+(?:job(?:\s+is)?|javis|jarvis)\s*[.!?]*\s*$", "danke dir Jarvis"),
    (r"(?i)\bdanke\s+dir\s+(?:jobs?|job(?:\s+is)?|javis)\b", "danke dir Jarvis"),
)

SHORT_HALLUCINATION_PATTERNS: tuple[str, ...] = (
    r"^(?:swr|ard|zdf|rtl|orf)\s*(?:\d{2,4})?$",
    r"^(?:swr|ard|zdf|rtl|orf)\s+\d{4}$",
    r"^\d{4}$",
)

_PIPER_VOICE_CACHE: dict[str, Any] = {}
_PIPER_VOICE_CACHE_LOCK = threading.Lock()
_PIPER_CMD_MODE_CACHE: dict[str, int] = {}
_PIPER_CMD_MODE_CACHE_LOCK = threading.Lock()


def _find_whisper_binary(configured_binary: str) -> str | None:
    return find_whisper_binary(configured_binary)


def _find_ffmpeg_binary() -> str | None:
    return find_system_tool("ffmpeg")


def _find_piper_binary() -> str | None:
    direct = shutil.which("piper")
    if direct:
        return direct

    venv_candidate = Path(sys.executable).resolve().parent / "piper"
    if venv_candidate.exists():
        return str(venv_candidate)

    return None


def _piper_cache_key(piper_command: list[str], model_path: Path) -> str:
    return f"{'|'.join(piper_command)}::{model_path}"


async def _load_cached_piper_voice(model_path: Path) -> Any:
    if PiperVoice is None:
        raise AudioError("Python-Piper API ist nicht verfuegbar.")

    key = str(model_path)
    with _PIPER_VOICE_CACHE_LOCK:
        cached = _PIPER_VOICE_CACHE.get(key)
    if cached is not None:
        return cached

    def _load() -> Any:
        return PiperVoice.load(str(model_path))

    loaded = await asyncio.to_thread(_load)
    with _PIPER_VOICE_CACHE_LOCK:
        existing = _PIPER_VOICE_CACHE.get(key)
        if existing is not None:
            return existing
        _PIPER_VOICE_CACHE[key] = loaded
    return loaded


def _clean_whisper_output(text: str) -> str:
    cleaned = re.sub(r"\[[^\]]+\]", "", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_for_matching(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9 ]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _apply_bavarian_normalization(text: str) -> str:
    normalized = text
    for pattern, replacement in BAVARIAN_TEXT_NORMALIZATIONS:
        normalized = re.sub(pattern, replacement, normalized)
    return _clean_whisper_output(normalized)


def _apply_common_stt_mishear_normalization(text: str) -> str:
    normalized = text
    for pattern, replacement in COMMON_STT_MISHEAR_NORMALIZATIONS:
        normalized = re.sub(pattern, replacement, normalized)
    return _clean_whisper_output(normalized)


def _looks_like_short_hallucination(text: str) -> bool:
    candidate = _normalize_for_matching(text)
    if not candidate:
        return False

    if len(candidate.split()) > 3:
        return False

    return any(re.fullmatch(pattern, candidate) for pattern in SHORT_HALLUCINATION_PATTERNS)


def _compact_error_message(text: str, *, limit: int = 300) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return "Unbekannter Fehler."
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _as_float(value: str | float | int | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: str | float | int | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _prepare_tts_text(
    text: str,
    *,
    sir_pronunciation: str,
) -> str:
    prepared = _clean_whisper_output(text)
    if not prepared:
        return prepared

    # Improve intelligibility before synthesis.
    prepared = re.sub(r"`([^`]+)`", r"\1", prepared)
    prepared = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", prepared)
    prepared = prepared.replace("&", " und ")
    prepared = prepared.replace("z.B.", "zum Beispiel")
    prepared = prepared.replace("bzw.", "beziehungsweise")
    prepared = prepared.replace("u.a.", "unter anderem")
    prepared = re.sub(r"\bca\.\b", "circa", prepared, flags=re.IGNORECASE)
    prepared = re.sub(r"(?i)\bqwen\b", "kuen", prepared)
    prepared = re.sub(r"\b(https?://\S+)\b", "Link", prepared)
    prepared = re.sub(r"\s+", " ", prepared).strip()

    if sir_pronunciation:
        # Keep UI text untouched but normalize spoken output for "Sir".
        prepared = re.sub(r"(?i)\bsir\b", sir_pronunciation, prepared)

    # Slightly clearer rhythm for German voices.
    prepared = re.sub(r"(?i)\b(ja|gut|perfekt|verstanden)\b[, ]*", r"\1, ", prepared)
    prepared = re.sub(r"\s+([,.;:!?])", r"\1", prepared)
    prepared = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", prepared)
    prepared = re.sub(r"\s+", " ", prepared).strip()

    return prepared


def _remove_path(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except Exception:
        return


def _cleanup_temp_directory(
    directory: Path,
    *,
    keep_entries: int,
    max_age_seconds: int,
) -> None:
    if not directory.exists():
        return

    now = time.time()
    entries: list[tuple[float, Path]] = []

    for entry in directory.iterdir():
        try:
            stat = entry.stat()
        except OSError:
            continue

        age_seconds = now - stat.st_mtime
        if max_age_seconds > 0 and age_seconds > max_age_seconds:
            _remove_path(entry)
            continue

        entries.append((stat.st_mtime, entry))

    entries.sort(key=lambda item: item[0], reverse=True)
    for _, entry in entries[max(1, keep_entries):]:
        _remove_path(entry)


def _run_temp_maintenance(config: AppConfig) -> None:
    try:
        _cleanup_temp_directory(
            config.audio_tmp_dir,
            keep_entries=DEFAULT_AUDIO_KEEP_ENTRIES,
            max_age_seconds=DEFAULT_TMP_MAX_AGE_SECONDS,
        )
    except Exception:
        pass
    try:
        _cleanup_temp_directory(
            config.tts_tmp_dir,
            keep_entries=DEFAULT_TTS_KEEP_ENTRIES,
            max_age_seconds=DEFAULT_TMP_MAX_AGE_SECONDS,
        )
    except Exception:
        pass


def normalize_transcript_text(text: str) -> str:
    normalized = _clean_whisper_output(text)
    if not normalized:
        return normalized

    alias_pattern = "|".join(re.escape(alias) for alias in WAKE_WORD_ALIASES)
    prefix_pattern = "|".join(re.escape(prefix) for prefix in WAKE_WORD_PREFIXES)
    command_pattern = "|".join(re.escape(item) for item in WAKE_WORD_COMMAND_HINTS)

    normalized = re.sub(
        rf"(?i)\b(?P<prefix>{prefix_pattern})\s+(?:{alias_pattern})\b",
        lambda match: f"{match.group('prefix')} {WAKE_WORD}",
        normalized,
    )

    normalized = re.sub(
        rf"(?i)^\s*(?:{alias_pattern})(?=(?:\s*[,:\-!?]|\s+(?:{command_pattern})\b|\s*$))",
        WAKE_WORD,
        normalized,
    )

    normalized = re.sub(
        rf"(?i)\b(?:{alias_pattern})\b(?=\s*[,:\-!?])",
        WAKE_WORD,
        normalized,
    )
    normalized = _apply_common_stt_mishear_normalization(normalized)
    normalized = _apply_bavarian_normalization(normalized)
    if _looks_like_short_hallucination(normalized):
        return ""

    return _clean_whisper_output(normalized)


async def _run_subprocess(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            input=input_text,
            text=True,
            capture_output=True,
        )

    return await asyncio.to_thread(_run)


async def _run_stt_subprocess(
    args: list[str],
    *,
    timeout_seconds: float,
    phase: str,
) -> subprocess.CompletedProcess[str]:
    """Own and reap STT child processes; never use an unbounded background thread."""
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
    except OSError as error:
        raise AudioError(f"{phase}: Programm konnte nicht gestartet werden: {error}") from error

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except (TimeoutError, asyncio.CancelledError) as error:
        if process.returncode is None:
            try:
                if os.name != "nt":
                    # Whisper/ffmpeg are their own process group. End children too.
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.communicate(), timeout=10)
        except (TimeoutError, RuntimeError):
            await process.wait()
        if isinstance(error, asyncio.CancelledError):
            raise
        raise AudioError(f"{phase}: Zeitlimit von {int(timeout_seconds)} Sekunden überschritten.") from error
    return subprocess.CompletedProcess(
        args, process.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _parse_say_voices(raw_output: str) -> list[str]:
    voices: list[str] = []
    seen: set[str] = set()

    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^(.+?)\s+([a-z]{2}(?:_[A-Za-z0-9]+)?)\s+#", line)
        if not match:
            continue

        voice_name = match.group(1).strip()
        if not voice_name or voice_name in seen:
            continue

        seen.add(voice_name)
        voices.append(voice_name)

    return voices


async def list_say_voices() -> list[str]:
    result = await _run_subprocess(["say", "-v", "?"])
    if result.returncode != 0:
        raise AudioError(_compact_error_message(result.stderr or "say Stimmen konnten nicht geladen werden."))

    voices = _parse_say_voices(result.stdout or "")
    if not voices:
        raise AudioError("Keine `say` Stimmen gefunden.")

    return voices


async def transcribe_with_whisper_cpp(
    *,
    source_path: Path,
    settings: dict[str, str],
    config: AppConfig,
) -> tuple[str, str, int]:
    started = time.perf_counter()
    _run_temp_maintenance(config)

    whisper_bin = _find_whisper_binary(str(settings.get("whisper_binary", "auto")))
    if not whisper_bin:
        raise AudioError("Whisper Binary nicht gefunden (erwartet: whisper-cli oder whisper-cpp).")

    model_path = Path(str(settings.get("whisper_model_path", "") or config.default_whisper_model)).expanduser().resolve()
    if not model_path.exists():
        raise AudioError(
            f"Whisper Modell fehlt: {model_path}. Bitte ein lokales ggml-Whisper-Modell herunterladen und Pfad setzen."
        )

    work_dir = config.audio_tmp_dir / uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    converted_path = work_dir / "input.wav"
    language = str(settings.get("language", "de"))
    whisper_prompt = str(
        settings.get(
            "whisper_prompt",
            "Jarvis, danke dir Jarvis. Deutsch mit bairischem Dialekt: servus, griass di, i, ned, net, koa, des, mei.",
        )
    ).strip()
    whisper_beam_size = max(1, _as_int(settings.get("whisper_beam_size"), DEFAULT_WHISPER_BEAM_SIZE))
    whisper_best_of = max(1, _as_int(settings.get("whisper_best_of"), DEFAULT_WHISPER_BEST_OF))
    whisper_no_speech_thold = _as_float(
        settings.get("whisper_no_speech_thold"),
        DEFAULT_WHISPER_NO_SPEECH_THOLD,
    )
    whisper_entropy_thold = _as_float(
        settings.get("whisper_entropy_thold"),
        DEFAULT_WHISPER_ENTROPY_THOLD,
    )
    whisper_logprob_thold = _as_float(
        settings.get("whisper_logprob_thold"),
        DEFAULT_WHISPER_LOGPROB_THOLD,
    )

    try:
        if source_path.suffix.lower() == ".wav":
            shutil.copyfile(source_path, converted_path)
        else:
            ffmpeg = _find_ffmpeg_binary()
            if not ffmpeg:
                raise AudioError("ffmpeg fehlt. Bitte über den System-Paketmanager oder Guided Setup installieren (Windows/macOS).")

            conversion = await _run_stt_subprocess(
                [
                    ffmpeg,
                    "-nostdin",
                    "-y",
                    "-i",
                    str(source_path),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(converted_path),
                ],
                timeout_seconds=STT_FFMPEG_TIMEOUT_SECONDS,
                phase="ffmpeg-Konvertierung",
            )

            if conversion.returncode != 0:
                raise AudioError(conversion.stderr.strip() or "Audio-Konvertierung fehlgeschlagen.")

        out_prefix = work_dir / "transcript"
        command = [
            whisper_bin,
            "-m",
            str(model_path),
            "-f",
            str(converted_path),
            "-l",
            language,
            "-bs",
            str(whisper_beam_size),
            "-bo",
            str(whisper_best_of),
            "-nth",
            str(whisper_no_speech_thold),
            "-et",
            str(whisper_entropy_thold),
            "-lpt",
            str(whisper_logprob_thold),
            "-tp",
            "0.0",
            "-nf",
            "-sns",
            "--prompt",
            whisper_prompt,
            "-otxt",
            "-of",
            str(out_prefix),
        ]

        result = await _run_stt_subprocess(
            command,
            timeout_seconds=STT_WHISPER_TIMEOUT_SECONDS,
            phase="Whisper-Inferenz",
        )
        if result.returncode != 0:
            raise AudioError(_compact_error_message(result.stderr or "Whisper Transkription fehlgeschlagen."))

        transcript_file = out_prefix.with_suffix(".txt")
        transcript_text = ""
        if transcript_file.exists():
            transcript_text = transcript_file.read_text(encoding="utf-8", errors="ignore")
        elif result.stdout:
            transcript_text = result.stdout

        transcript_text = normalize_transcript_text(transcript_text)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return transcript_text, language, latency_ms
    finally:
        _remove_path(work_dir)


async def speak_text(
    *,
    text: str,
    settings: dict[str, str],
    config: AppConfig,
) -> int:
    started = time.perf_counter()
    _run_temp_maintenance(config)

    tts_engine = str(settings.get("tts_engine", "piper")).strip().lower()
    tts_voice = str(settings.get("tts_voice", "de_DE-thorsten-high"))
    tts_sir_pronunciation = str(settings.get("tts_sir_pronunciation", "Sör")).strip() or "Sör"
    tts_text = _prepare_tts_text(
        text,
        sir_pronunciation=tts_sir_pronunciation,
    )
    if not tts_text:
        raise AudioError("Leerer TTS-Text nach Normalisierung.")

    if tts_engine == "say":
        say_rate_wpm = max(80, min(420, _as_int(settings.get("say_rate_wpm"), DEFAULT_SAY_RATE_WPM)))
        say_command = ["say", "-v", tts_voice, "-r", str(say_rate_wpm), tts_text]
        process = await _run_subprocess(say_command)
        if process.returncode != 0:
            raise AudioError(_compact_error_message(process.stderr or "say fehlgeschlagen"))
        return int((time.perf_counter() - started) * 1000)

    if tts_engine != "piper":
        raise AudioError(f"Unbekannte TTS Engine: {tts_engine}")

    model_path_value = str(settings.get("tts_model_path", "")).strip()
    if not model_path_value:
        raise AudioError("tts_model_path ist leer. Bitte in Settings setzen.")

    model_path = Path(model_path_value).expanduser().resolve()
    if not model_path.exists():
        raise AudioError(f"Piper Modell nicht gefunden: {model_path}")

    length_scale = _as_float(settings.get("piper_length_scale"), DEFAULT_PIPER_LENGTH_SCALE)
    noise_scale = _as_float(settings.get("piper_noise_scale"), DEFAULT_PIPER_NOISE_SCALE)
    noise_w_scale = _as_float(settings.get("piper_noise_w_scale"), DEFAULT_PIPER_NOISE_W_SCALE)
    sentence_silence = _as_float(settings.get("piper_sentence_silence"), DEFAULT_PIPER_SENTENCE_SILENCE)
    volume = _as_float(settings.get("piper_volume"), DEFAULT_PIPER_VOLUME)

    output_wav = config.tts_tmp_dir / f"tts-{uuid4().hex}.wav"
    try:
        used_python_api = False
        python_api_error: str | None = None

        if DEFAULT_PIPER_USE_PYTHON_API and PiperVoice is not None and SynthesisConfig is not None:
            try:
                piper_voice = await _load_cached_piper_voice(model_path)

                def _synthesize_with_python_api() -> None:
                    _remove_path(output_wav)
                    synthesis_config = SynthesisConfig(
                        length_scale=length_scale,
                        noise_scale=noise_scale,
                        noise_w_scale=noise_w_scale,
                        volume=volume,
                    )
                    with wave.open(str(output_wav), "wb") as wav_file:
                        piper_voice.synthesize_wav(
                            text=tts_text,
                            wav_file=wav_file,
                            syn_config=synthesis_config,
                        )

                await asyncio.to_thread(_synthesize_with_python_api)
                if output_wav.exists() and output_wav.stat().st_size > 0:
                    used_python_api = True
                else:
                    python_api_error = "Python-Piper API erzeugte keine Audiodatei."
            except Exception as error:
                python_api_error = str(error)

        if not used_python_api:
            # CLI fallback (and compatibility path).
            piper_binary = _find_piper_binary()
            piper_command: list[str]
            if piper_binary:
                piper_command = [piper_binary]
            else:
                piper_command = [sys.executable, "-m", "piper"]
                probe = await _run_subprocess([*piper_command, "--help"])
                if probe.returncode != 0:
                    raise AudioError(
                        "Piper nicht gefunden. Bitte `pip install piper-tts` im Agent-Python ausfuehren."
                    )

            prosody_args = [
                "--length-scale",
                str(length_scale),
                "--noise-scale",
                str(noise_scale),
                "--noise-w-scale",
                str(noise_w_scale),
                "--sentence-silence",
                str(sentence_silence),
                "--volume",
                str(volume),
            ]

            # Piper CLI exists in multiple incompatible variants.
            # Try a small command matrix so TTS keeps working across builds.
            synth_attempt_templates = [
                [*piper_command, "--model", str(model_path), *prosody_args, "--output_file", str(output_wav)],
                [*piper_command, "-m", str(model_path), *prosody_args, "-f", str(output_wav)],
                [*piper_command, "--model", str(model_path), "--output_file", str(output_wav)],
                [*piper_command, "-m", str(model_path), "-f", str(output_wav)],
            ]

            cache_key = _piper_cache_key(piper_command, model_path)
            with _PIPER_CMD_MODE_CACHE_LOCK:
                preferred_index = _PIPER_CMD_MODE_CACHE.get(cache_key)

            ordered_attempts: list[tuple[int, list[str]]] = []
            if preferred_index is not None and 0 <= preferred_index < len(synth_attempt_templates):
                ordered_attempts.append((preferred_index, synth_attempt_templates[preferred_index]))

            for index, template in enumerate(synth_attempt_templates):
                if preferred_index is not None and index == preferred_index:
                    continue
                ordered_attempts.append((index, template))

            synthesis: subprocess.CompletedProcess[str] | None = None
            successful_mode_index: int | None = None
            for mode_index, command in ordered_attempts:
                _remove_path(output_wav)
                synthesis = await _run_subprocess(command, input_text=tts_text)
                if synthesis.returncode == 0 and output_wav.exists() and output_wav.stat().st_size > 0:
                    successful_mode_index = mode_index
                    break

            if successful_mode_index is not None:
                with _PIPER_CMD_MODE_CACHE_LOCK:
                    _PIPER_CMD_MODE_CACHE[cache_key] = successful_mode_index
            else:
                error_parts: list[str] = []
                if synthesis is not None:
                    error_parts.append(synthesis.stderr or synthesis.stdout or "")
                if python_api_error:
                    error_parts.append(f"Python-API: {python_api_error}")
                raise AudioError(
                    _compact_error_message(
                        " | ".join(part for part in error_parts if part) or "Piper Synthese fehlgeschlagen"
                    )
                )

        if not output_wav.exists() or output_wav.stat().st_size <= 0:
            raise AudioError("Piper Synthese lieferte keine Audiodatei.")

        if sys.platform == "darwin":
            playback = await _run_subprocess(["afplay", str(output_wav)])
            if playback.returncode != 0:
                raise AudioError(_compact_error_message(playback.stderr or playback.stdout or "Audio Playback fehlgeschlagen"))
        else:
            from .audio_playback import play_wav
            try:
                await asyncio.to_thread(play_wav, output_wav)
            except Exception as error:
                raise AudioError(f"Audioausgabe fehlgeschlagen: {error}") from error
    finally:
        _remove_path(output_wav)

    return int((time.perf_counter() - started) * 1000)
