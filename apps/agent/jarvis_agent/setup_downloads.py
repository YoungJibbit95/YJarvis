"""Bounded downloads and extraction for explicit setup requests, never planner tools."""
from __future__ import annotations

import hashlib
import asyncio
import json
import os
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable

import httpx


Progress = Callable[[int, int | None], None]


def source_url(url: str) -> None:
    parsed = httpx.URL(url)
    host = parsed.host
    allowed = ("huggingface.co", "github.com", "api.github.com", "objects.githubusercontent.com",
               "release-assets.githubusercontent.com", "cdn-lfs.huggingface.co")
    if parsed.scheme != "https" or parsed.userinfo or not (
        host in allowed or host.endswith(".hf.co") or host.endswith(".huggingface.co")
    ):
        raise ValueError("Unzulässige Downloadquelle")


async def open_source(client: httpx.AsyncClient, url: str) -> httpx.Response:
    for _ in range(10):
        source_url(url)
        response = await client.send(client.build_request("GET", url), stream=True)
        if response.is_redirect:
            next_url = str(response.url.join(response.headers["location"]))
            await response.aclose()
            url = next_url
            continue
        try:
            response.raise_for_status()
        except Exception:
            await response.aclose()
            raise ValueError(f"Downloadquelle antwortet mit HTTP {response.status_code}") from None
        return response
    raise ValueError("Zu viele Download-Weiterleitungen")


async def source_json(client: httpx.AsyncClient, url: str, limit: int = 16_000_000):
    response = await open_source(client, url)
    try:
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError("Quellen-Metadaten sind zu groß")
        return json.loads(data)
    finally:
        await response.aclose()


def digest_file(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def download(client: httpx.AsyncClient, url: str, target: Path, sha256: str,
                   size: int, progress: Progress) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", sha256) or not 0 < size <= 16_000_000_000:
        raise ValueError("Download hat keine gültige Größe/SHA256")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("Downloadziel darf kein Symlink sein")
    if target.exists() and target.stat().st_size == size and await asyncio.to_thread(digest_file, target) == sha256:
        progress(size, size)
        return target
    if shutil.disk_usage(target.parent).free < size + 128_000_000:
        raise ValueError("Nicht genug freier Speicherplatz für diesen Download")
    partial = target.with_name(target.name + ".part")
    if partial.is_symlink():
        raise ValueError("Temporäres Downloadziel ist ein Symlink")
    response = await open_source(client, url)
    total = 0
    digest = hashlib.sha256()
    try:
        with partial.open("wb") as stream:
            async for chunk in response.aiter_bytes(1024 * 1024):
                total += len(chunk)
                if total > size:
                    raise ValueError("Download überschreitet die angekündigte Größe")
                stream.write(chunk)
                digest.update(chunk)
                progress(total, size)
        if total != size or digest.hexdigest() != sha256:
            raise ValueError("Download-Größe oder SHA256 stimmt nicht")
        os.replace(partial, target)
        return target
    finally:
        await response.aclose()
        partial.unlink(missing_ok=True)


def extract_archive(archive: Path, destination: Path) -> None:
    """Preflight every member before writing; never trust ZIP paths or links."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zip_file:
        members = zip_file.infolist()
        if len(members) > 10000 or sum(member.file_size for member in members) > 24_000_000_000:
            raise ValueError("Archiv ist zu groß")
        if shutil.disk_usage(root).free < sum(member.file_size for member in members) + 128_000_000:
            raise ValueError("Nicht genug Platz zum Entpacken")
        for member in members:
            pure = PurePosixPath(member.filename)
            if (pure.is_absolute() or ".." in pure.parts or "\\" in member.filename
                    or ":" in member.filename or (member.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsicherer Archivpfad")
            target = root.joinpath(*pure.parts)
            if not target.resolve().is_relative_to(root) or target.is_symlink():
                raise ValueError("Archivpfad verlässt das Installationsziel")
        zip_file.extractall(root)


async def repository_file(client: httpx.AsyncClient, repo: str, filename: str,
                          target: Path, progress: Progress) -> Path:
    info = await source_json(client, f"https://huggingface.co/api/models/{repo}?blobs=true")
    revision = info["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Ungültige Modellrevision")
    metadata = next((item for item in info["siblings"] if item["rfilename"] == filename), None)
    if not metadata:
        raise ValueError("Modelldatei fehlt in der offiziellen Quelle")
    lfs = metadata.get("lfs")
    if lfs:
        sha256, size = lfs["sha256"], lfs["size"]
    else:
        # Small configuration/model-card files use Git blob SHA1. Fetch the
        # immutable revision, verify that identity, then store by SHA256.
        response = await open_source(client, f"https://huggingface.co/{repo}/resolve/{revision}/{filename}")
        try:
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 2_000_000:
                    raise ValueError("Konfigurationsdatei ist zu groß")
            blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            if blob != metadata["blobId"]:
                raise ValueError("Konfigurationsdatei stimmt nicht mit der Revision überein")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or target.parent.is_symlink():
                raise ValueError("Unsicheres Konfigurationsziel")
            temp = target.with_name(target.name + ".part")
            if temp.is_symlink():
                raise ValueError("Unsicheres temporäres Ziel")
            try:
                temp.write_bytes(data)
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
            return target
        finally:
            await response.aclose()
    return await download(client, f"https://huggingface.co/{repo}/resolve/{revision}/{filename}",
                          target, sha256, size, progress)
