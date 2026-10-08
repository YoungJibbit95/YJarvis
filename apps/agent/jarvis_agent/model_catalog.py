"""Validated descriptive model metadata. No runtime, discovery or acquisition code."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(min_length=1, pattern=r"^\S(?:[^\r\n]*\S)?$")]
CatalogId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
PositiveCount = Annotated[int, Field(gt=0)]
ModelCategory = Literal["chat", "speech_to_text", "text_to_speech"]


class CatalogValue(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, validate_default=True,
        protected_namespaces=("model_validate", "model_dump"),
    )


class ModelSource(CatalogValue):
    publisher: Text
    url: HttpUrl
    checked_on: date

    @field_validator("url")
    @classmethod
    def descriptive_https_source(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.username or value.password or value.query or value.fragment:
            raise ValueError("Sources must be HTTPS pages without credentials, query or fragment")
        return value


class ModelLicense(CatalogValue):
    # Null means the cited source does not establish a license for this scope.
    name: Text | None
    scope: Literal["model", "dataset"]
    source: ModelSource


class RuntimeModel(CatalogValue):
    backend: Literal["ollama", "whisper_cpp", "piper"]
    model_id: Text


class ModelAcquisition(CatalogValue):
    mechanism: Literal["ollama_library", "hugging_face_files"]
    source: ModelSource
    approximate_download_bytes: PositiveCount | None = None

    @model_validator(mode="after")
    def source_matches_mechanism(self) -> Self:
        host = "ollama.com" if self.mechanism == "ollama_library" else "huggingface.co"
        if self.source.url.host != host:
            raise ValueError("Acquisition source does not match its mechanism")
        return self


class ModelCatalogEntry(CatalogValue):
    id: CatalogId
    category: ModelCategory
    display_name: Text
    publisher: Text
    model_id: Text
    description: Text
    source: ModelSource
    licenses: Annotated[tuple[ModelLicense, ...], Field(min_length=1)]
    runtime: RuntimeModel
    acquisition: ModelAcquisition
    context_window_tokens: PositiveCount | None = None
    # A publisher's own variant label, never a cross-model quality/speed ranking.
    publisher_quality_label: Text | None = None

    @model_validator(mode="after")
    def coherent_metadata(self) -> Self:
        expected = {
            "chat": ("ollama", "ollama_library"),
            "speech_to_text": ("whisper_cpp", "hugging_face_files"),
            "text_to_speech": ("piper", "hugging_face_files"),
        }
        if (self.runtime.backend, self.acquisition.mechanism) != expected[self.category]:
            raise ValueError("Unsupported category/backend/acquisition combination")
        scopes = [license.scope for license in self.licenses]
        if "model" not in scopes or len(scopes) != len(set(scopes)):
            raise ValueError("Exactly one model license statement is required; scopes must be unique")
        if self.category != "chat" and self.context_window_tokens is not None:
            raise ValueError("Token context applies only to chat entries")
        return self


class ModelCatalog(CatalogValue):
    entries: Annotated[tuple[ModelCatalogEntry, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_identifiers(self) -> Self:
        ids = [entry.id for entry in self.entries]
        runtime_ids = [(entry.runtime.backend, entry.runtime.model_id) for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate catalog id")
        if len(runtime_ids) != len(set(runtime_ids)):
            raise ValueError("Duplicate backend/model id")
        return self

    def get(self, catalog_id: str) -> ModelCatalogEntry:
        for entry in self.entries:
            if entry.id == catalog_id:
                return entry
        raise KeyError(catalog_id)
