"""Small reviewed catalog, usable offline. Source pages are never fetched here."""
from datetime import date

from .model_catalog import ModelCatalog, ModelCatalogEntry, ModelSource


def _source(publisher: str, url: str) -> ModelSource:
    return ModelSource(publisher=publisher, url=url, checked_on=date(2026, 10, 8))


_qwen = _source("Qwen", "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct")
_whisper = _source("OpenAI", "https://github.com/openai/whisper")
_thorsten = _source(
    "Rhasspy / Piper",
    "https://huggingface.co/rhasspy/piper-voices/blob/main/de/de_DE/thorsten/medium/MODEL_CARD",
)

BUNDLED_MODEL_CATALOG = ModelCatalog(entries=(
    ModelCatalogEntry(
        id="qwen25-3b-instruct-ollama",
        category="chat",
        display_name="Qwen2.5 3B Instruct",
        publisher="Qwen / Alibaba Cloud",
        model_id="Qwen/Qwen2.5-3B-Instruct",
        description="Mehrsprachiges Modell für textbasierte Gespräche, auch auf Deutsch.",
        source=_qwen,
        licenses=({
            "name": "Qwen Research License Agreement", "scope": "model",
            "source": _source("Qwen", "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE"),
        },),
        runtime={"backend": "ollama", "model_id": "qwen2.5:3b-instruct"},
        acquisition={
            "mechanism": "ollama_library",
            "source": _source("Ollama", "https://ollama.com/library/qwen2.5:3b-instruct"),
            "approximate_download_bytes": 1_900_000_000,
        },
        context_window_tokens=32_768,
    ),
    ModelCatalogEntry(
        id="whisper-small-ggml",
        category="speech_to_text",
        display_name="Whisper Small",
        publisher="OpenAI",
        model_id="openai/whisper-small",
        description="Mehrsprachige Spracherkennung: wandelt gesprochene Sprache in Text um.",
        source=_whisper,
        licenses=({"name": "MIT", "scope": "model", "source": _whisper},),
        runtime={"backend": "whisper_cpp", "model_id": "ggml-small.bin"},
        acquisition={
            "mechanism": "hugging_face_files",
            "source": _source("ggerganov / whisper.cpp", "https://huggingface.co/ggerganov/whisper.cpp/blob/main/ggml-small.bin"),
            "approximate_download_bytes": 488_000_000,
        },
    ),
    ModelCatalogEntry(
        id="piper-de-thorsten-medium",
        category="text_to_speech",
        display_name="Thorsten · Deutsch",
        publisher="Rhasspy / Piper",
        model_id="rhasspy/piper-voices/de/de_DE/thorsten/medium",
        description="Deutsche Stimme für die lokale Sprachausgabe mit Piper.",
        source=_thorsten,
        # The voice card names a dataset license, not an explicit model-weight license.
        licenses=(
            {"name": None, "scope": "model", "source": _thorsten},
            {"name": "CC0", "scope": "dataset", "source": _thorsten},
        ),
        runtime={"backend": "piper", "model_id": "de_DE-thorsten-medium"},
        acquisition={
            "mechanism": "hugging_face_files",
            "source": _source("Rhasspy / Piper", "https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE/thorsten/medium"),
        },
        publisher_quality_label="medium",
    ),
))
