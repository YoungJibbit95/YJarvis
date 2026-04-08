from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .db import Database


class SmartHomeProvider(ABC):
    @abstractmethod
    async def list_entities(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def call_service(self, entity_id: str, service: str) -> dict[str, Any]:
        raise NotImplementedError


class HomeAssistantStubProvider(SmartHomeProvider):
    def __init__(self, db: Database) -> None:
        self.db = db

    async def list_entities(self) -> list[dict[str, Any]]:
        return await self.db.list_smarthome_entities()

    async def call_service(self, entity_id: str, service: str) -> dict[str, Any]:
        entity = await self.db.get_smarthome_entity(entity_id)
        if entity is None:
            raise ValueError(f"Entity nicht gefunden: {entity_id}")

        current_state = str(entity.get("state", "off"))
        attributes = dict(entity.get("attributes", {}))

        if service == "toggle":
            next_state = "off" if current_state == "on" else "on"
        elif service == "turn_on":
            next_state = "on"
        elif service == "turn_off":
            next_state = "off"
        else:
            raise ValueError(f"Unbekannter Service: {service}")

        if entity.get("entity_type") == "light":
            attributes["brightness"] = 100 if next_state == "on" else 0

        updated = await self.db.update_smarthome_entity(
            entity_id=entity_id,
            state=next_state,
            attributes=attributes,
        )

        if updated is None:
            raise ValueError(f"Entity konnte nicht aktualisiert werden: {entity_id}")

        return updated
