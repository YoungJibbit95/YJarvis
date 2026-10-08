"""Explicit desktop setup transport; browser-origin guard on all mutations."""
from fastapi import APIRouter, HTTPException, Request, Response
import httpx

from .setup_components import voices, WHISPER_MODELS
from .setup_installation import InstallSelection, SetupInstaller


def create_install_router(installer: SetupInstaller) -> APIRouter:
    router = APIRouter(prefix="/v1/setup/install")

    def desktop_request(request: Request):
        if request.headers.get("origin") not in {"app://yjarvis", "http://127.0.0.1:5173", "http://localhost:5173"}:
            raise HTTPException(403, "Installation ist nur über die lokale Desktop-Einrichtung erlaubt")

    @router.get("/options")
    async def options(response: Response):
        response.headers["Cache-Control"] = "no-store"
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                catalog = await voices(client)
            return {"whisper_models": WHISPER_MODELS, "voices": [
                {"id": key, "name": f"{entry['language']['name_native']} · {entry['name']} · {entry['quality']}"}
                for key, entry in sorted(catalog.items())
            ]}
        except Exception:
            raise HTTPException(503, "Stimmenkatalog nicht erreichbar. Bitte erneut laden.") from None

    @router.get("")
    async def status(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return dict(installer.state)

    @router.post("")
    async def start(selection: InstallSelection, request: Request):
        desktop_request(request)
        try:
            return installer.start(selection)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.delete("")
    async def cancel(request: Request):
        desktop_request(request)
        return await installer.cancel()

    return router
