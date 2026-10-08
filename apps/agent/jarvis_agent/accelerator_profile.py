"""Read-only adapter facts, separate from hardware baseline and model suitability."""
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MemoryBytes = Annotated[int, Field(ge=0, le=2**53 - 1)]


class AcceleratorAdapter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    display_name: Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
    dedicated_video_memory_bytes: MemoryBytes | None
    shared_system_memory_bytes: MemoryBytes | None
    classification: Literal["hardware", "software", "unknown"]


class AcceleratorProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    status: Literal["available", "unknown", "unsupported"]
    adapters: Annotated[tuple[AcceleratorAdapter, ...], Field(max_length=64)]

    @model_validator(mode="after")
    def unavailable_has_no_adapters(self) -> Self:
        if self.status != "available" and self.adapters:
            raise ValueError("Unavailable enumeration cannot contain adapter facts")
        return self
