"""Descriptive setup hardware values; not capability availability or recommendations."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["windows", "macos", "linux", "unknown"]
Architecture = Literal["x86_64", "arm64", "other", "unknown"]
PositiveCount = Annotated[int, Field(gt=0, le=2**53 - 1)]
StorageBytes = Annotated[int, Field(ge=0, le=2**53 - 1)]


class HardwareProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    platform: Platform
    architecture: Architecture
    logical_cpu_count: PositiveCount | None
    total_memory_bytes: PositiveCount | None
    available_storage_bytes: StorageBytes | None
    storage_path_scope: Literal["app_runtime_directory"]
