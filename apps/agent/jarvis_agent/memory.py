from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import Database


def _parse_timestamp(timestamp: str) -> datetime:
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        return datetime.now(timezone.utc)


async def load_context_snippets(
    db: Database,
    user_input: str,
    limit: int = 4,
    *,
    session_id: str | None = None,
) -> list[str]:
    # Scoped prompt recall must not pull private memories from another session.
    if session_id is None:
        rows = await db.search_memory(user_input, limit=limit)
    else:
        rows = await db.search_memory(user_input, limit=limit, session_id=session_id)
    if not rows:
        return []

    now = datetime.now(timezone.utc)
    scored: list[tuple[float, str]] = []

    for row in rows:
        created_at = _parse_timestamp(str(row.get("created_at", "")))
        age_hours = max((now - created_at).total_seconds() / 3600.0, 0.0)
        recency_score = 1.0 / (1.0 + age_hours)
        importance = float(row.get("importance", 0.5))
        rank = float(row.get("rank", 0.0))
        text_rank_score = 1.0 if rank == 0.0 else min(1.0, 1.0 / (1.0 + abs(rank)))

        score = (importance * 0.45) + (recency_score * 0.35) + (text_rank_score * 0.20)
        scored.append((score, str(row.get("content", ""))))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [content for _, content in scored[:limit] if content]


def _summarize_messages(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "unknown")).upper()
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"{role}: {content[:280]}")
    return "\n".join(lines)


async def maybe_compact_session(db: Database, session_id: str) -> None:
    count = await db.count_messages(session_id)
    if count < 8 or count % 8 != 0:
        return

    recent = await db.list_recent_messages(session_id, limit=8)
    if not recent:
        return

    summary = _summarize_messages(recent)
    if not summary:
        return

    memory_text = "Kompakte Verlaufserinnerung:\n" + summary
    await db.add_memory_item(session_id=session_id, content=memory_text, importance=0.72)
