from __future__ import annotations

from pathlib import Path


def resolve_path(raw_path: str) -> Path:
    return Path(raw_path).expanduser().resolve()


def is_path_allowed(target: Path, allowed_paths: list[str]) -> bool:
    if not allowed_paths:
        return False

    for allowed in allowed_paths:
        try:
            allowed_path = resolve_path(allowed)
            if target == allowed_path or allowed_path in target.parents:
                return True
        except Exception:
            continue
    return False
