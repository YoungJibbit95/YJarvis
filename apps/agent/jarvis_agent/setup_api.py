"""Setup transport, deliberately separate from turn orchestration and action contracts."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Response

from .bundled_model_catalog import BUNDLED_MODEL_CATALOG
from .model_catalog import ModelCatalog
from .setup_readiness import SetupStatus, inspect_setup


def create_setup_router(
    read_settings: Callable[[], Awaitable[dict[str, Any]]],
    default_whisper_model: Path,
) -> APIRouter:
    router = APIRouter(prefix="/v1/setup")

    @router.get("/models", response_model=ModelCatalog)
    async def setup_models() -> ModelCatalog:
        return BUNDLED_MODEL_CATALOG

    @router.get("/status", response_model=SetupStatus)
    async def setup_status(response: Response) -> SetupStatus:
        response.headers["Cache-Control"] = "no-store"
        return await inspect_setup(await read_settings(), default_whisper_model)

    return router
