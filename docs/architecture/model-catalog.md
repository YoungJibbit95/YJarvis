# YJUX-02A: curated local model catalog

This step supplies three descriptive entries and a validated, offline Python
contract. It does not change startup, settings, readiness, model selection or
the UI. The optional browse UI is deferred to a separately authorized YJUX-02B.

## Baseline and ownership

Base main: `b553e44a52d37d37ec6a2bb0baae64f366c0ee44`, after accepted Core #16
and Product #15. The required sequence completed before this branch began:

- #16 squash main `eab1326`: [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37743515227).
- #15 synchronized head `f76779e`: exactly the twelve #16 files added; Product
  patch unchanged; [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37743787858).
- #15 squash main `b553e44`: identical combined tree; [6/6 CI](https://github.com/YoungJibbit95/YJarvis/actions/runs/37744058908).

Relative to architecture baseline `dea0e9e`, this includes the accepted CI,
domain, persistence, orchestration/router/planner extractions, Windows startup,
typed capability contracts, design foundations, shell and setup-readiness steps.
No Core PR was open at branch creation; the Core checkout had only a concurrent
README change. This PR adds isolated catalog modules, tests and this note.
It changes no Core Domain/ToolRuntime, shared backend file or existing UI file.

## Contract

`jarvis_agent.model_catalog.ModelCatalogEntry` contains:

| Field | Meaning |
| --- | --- |
| `id` | Stable, lowercase catalog key; not a runtime identifier or URL |
| `category` | `chat`, `speech_to_text`, or `text_to_speech` |
| `display_name`, `description`, `publisher` | Short display text and model publisher |
| `model_id`, `source` | Upstream model identity and its authoritative description |
| `licenses` | Explicit `model`/`dataset` scope, name or null, and evidence source |
| `runtime.backend`, `runtime.model_id` | Existing backend family and its model identifier; never a local path |
| `acquisition.mechanism`, `.source` | Descriptive `ollama_library` or `hugging_face_files` route and curated page |
| `acquisition.approximate_download_bytes` | Rounded source size converted to decimal bytes, or null; not required RAM or installed size |
| `context_window_tokens` | Publisher's model-specific chat context capacity, or null; not configured runtime context |
| `publisher_quality_label` | Optional publisher variant label, not a cross-model rating |

Every source records its publisher/distributor, HTTPS page and `checked_on` date.
Links contain no credentials, query or fragment. Acquisition hosts must match
the mechanism. The contract validates current category/backend/mechanism pairs;
adding another backend requires a reviewed contract extension, not an implicit
Ollama fallback. It does not detect or activate that backend on the host.

Models are strict, frozen Pydantic values with immutable tuples and forbidden
extra fields. Invalid types, categories, combinations, empty strings, license
scope duplication, non-positive sizes/context and duplicate catalog or
`(backend, model_id)` identities fail validation. Every entry explicitly states
a model license, including null when unknown. Upstream identity may be shared
by future distinct runtime variants; concrete runtime identities must be unique.

The bundled constant validates at import and provides exact lookup:

```python
from jarvis_agent.bundled_model_catalog import BUNDLED_MODEL_CATALOG

entries = BUNDLED_MODEL_CATALOG.entries
entry = BUNDLED_MODEL_CATALOG.get("whisper-small-ggml")
payload = BUNDLED_MODEL_CATALOG.model_dump_json()
```

Unknown keys raise `KeyError`; no fuzzy/default/URL lookup exists. There is no
registration API, HTTP route, remote refresh, user-supplied catalog or URL input.
The schema validates data shape; it does not authenticate publisher ownership.
Source provenance is curated through review of the committed bundle and the
official references below. These links are documentation, not download commands
or a verified installation manifest.

## Sources verified on 2026-10-08

### Qwen2.5 3B Instruct

- [Qwen publisher model card](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct):
  identity, publisher, instruction-tuned multilingual text model (including
  German), and **32,768 tokens for this 3B variant**. The family-wide 128K claim
  is not used for this entry.
- [Publisher license](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE):
  **Qwen Research License Agreement**; do not substitute the Apache license
  used by other Qwen2.5 sizes. The catalog makes no legal suitability judgment.
- [Official Ollama library variant](https://ollama.com/library/qwen2.5:3b-instruct):
  runtime ID `qwen2.5:3b-instruct`, Q4_K_M artifact, displayed approximate 1.9 GB
  represented as 1,900,000,000 bytes. Tags can move; this is a dated observation,
  not an immutable artifact pin. The existing configured model is not changed.

### Whisper Small (GGML)

- [OpenAI Whisper](https://github.com/openai/whisper): original model family,
  multilingual `small` variant and explicit MIT release of code and weights.
- [whisper.cpp model documentation](https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md)
  explicitly links the [ggerganov distribution](https://huggingface.co/ggerganov/whisper.cpp).
  This establishes the conversion source, separate from publisher OpenAI.
- [Concrete GGML file page](https://huggingface.co/ggerganov/whisper.cpp/blob/main/ggml-small.bin):
  `ggml-small.bin`, rounded 488 MB represented as 488,000,000 bytes. This is the
  file format already used by the legacy whisper.cpp path, not Transformers.
  The converted-model repository also labels its license MIT. The separate
  `openai/whisper-small` Hugging Face Transformers page has an Apache-2.0 header;
  that header is not treated as the license of this selected GGML distribution.

### Thorsten medium (Piper)

- [Piper's official voice documentation](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md)
  links the Rhasspy voice repository and requires an ONNX model plus its JSON
  configuration. Backend code licensing is not substituted for voice licensing.
- [Exact voice card](https://huggingface.co/rhasspy/piper-voices/blob/main/de/de_DE/thorsten/medium/MODEL_CARD):
  German `de_DE`, one speaker, publisher quality label `medium`, dataset CC0.
  CC0 is recorded **only with dataset scope**. The card does not separately
  establish a model-weight license; the model license remains null. The
  repository-wide MIT header is not silently applied to every voice.
- [Exact directory](https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE/thorsten/medium):
  distributor Rhasspy/Piper, `de_DE-thorsten-medium.onnx` and matching
  `.onnx.json`. The runtime identifier is the voice stem, not an install path.
  Total required download size stays null; no sum is inferred from the directory
  total, which also includes samples. This entry does not select this voice or
  replace the existing emotional voice preference.

## Unknowns and boundaries

Speed tiers, comparable quality tiers, RAM/VRAM needs, CPU/GPU/platform
availability and measured latency are unknown and deliberately have no fields
or ranking in this step. Piper's own `medium` label is not a recommendation.
Model revisions, checksums, install sizes and artifact manifests are omitted;
source verification here means reading metadata, not downloading/verifying
weights. Optional context/quality/size values serialize as null when unknown.

- Catalog entry **does not mean installed**.
- Catalog entry **does not mean available on this hardware**.
- Catalog entry **does not mean download/installation**.

Import, lookup and serialization need no network, backend, settings, database,
model files or process. Only normal Python module loading occurs (the cold-import
test disables interpreter bytecode writes). There is no downloader, directory
creation, installer, progress, removal, recommendation, auto-selection or runtime
execution. The existing YJUX-01A local inventory/file inspection remains the
readiness authority; catalog entries never feed its state calculation.

## Verification and rollback

`tests/test_model_catalog.py` covers validation, uniqueness, immutable nested
data, unknown lookups, cold import with network/process/write boundaries blocked,
offline JSON serialization and unchanged real readiness with mocked local
inventory both empty and populated. Existing readiness tests run unchanged.
The full Python/startup/typecheck/build suites remain required.

No model inference, native voice playback, macOS/Apple Silicon integration or
packaged-app behavior is proven by metadata tests. Revert this step's commit to
remove the catalog; no migration or runtime/model/user-data cleanup is needed.
