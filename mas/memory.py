"""Shared key/value store that all agents read from and write to."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .logger import AgentLogger


@dataclass
class MemoryEntry:
    key: str
    value: str
    owner_id: str
    version: int = 1
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SharedMemory:

    def __init__(self, logger: "AgentLogger | None" = None):
        self._store: dict[str, MemoryEntry] = {}
        self._log = logger

    def write(self, key: str, value: str, writer_id: str) -> None:
        existing = self._store.get(key)
        if existing:
            existing.value = value
            existing.version += 1
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self._store[key] = MemoryEntry(key=key, value=value, owner_id=writer_id)
        if self._log:
            self._log.memory_write(writer_id, key, value)

    def get_all(self) -> dict[str, MemoryEntry]:
        return dict(self._store)
