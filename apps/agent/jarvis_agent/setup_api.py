"""Setup transport, deliberately separate from turn orchestration and action contracts."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Response

from .bundled_model_catalog import BUNDLED_MODEL_CATALOG
from .model_catalog import ModelCatalog
from .hardware_profile import HardwareProfile
from .accelerator_profile import AcceleratorProfile
from .setup_accelerators import inspect_accelerators
from .setup_hardware import inspect_hardware
from .setup_readiness import SetupStatus, inspect_setup, ComponentStatus, combine_status


def create_setup_router(
    read_settings: Callable[[], Awaitable[dict[str, Any]]],
    default_whisper_model: Path,
    runtime_dir: Path | None = None,
    voice_verified: Callable[[dict[str, Any]], bool] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/setup")

    @router.get("/accelerators", response_model=AcceleratorProfile)
    def setup_accelerators(response: Response) -> AcceleratorProfile:
        response.headers["Cache-Control"] = "no-store"
        return inspect_accelerators()

    @router.get("/hardware", response_model=HardwareProfile)
    def setup_hardware(response: Response) -> HardwareProfile:
        response.headers["Cache-Control"] = "no-store"
        return inspect_hardware(runtime_dir)

    @router.get("/models", response_model=ModelCatalog)
    async def setup_models() -> ModelCatalog:
        return BUNDLED_MODEL_CATALOG

    @router.get("/status", response_model=SetupStatus)
    async def setup_status(response: Response) -> SetupStatus:
        response.headers["Cache-Control"] = "no-store"
        settings = await read_settings()
        report = await inspect_setup(settings, default_whisper_model)
        if voice_verified and report.tts.reason == "voice_unverified" and voice_verified(settings):
            return combine_status(report.chat_model, report.stt, ComponentStatus(status="available", reason="voice_verified_during_setup"))
        return report

    return router
