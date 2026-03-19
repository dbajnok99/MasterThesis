"""
Shared memory store.

A simple key/value store that all agents can read from and write to.
This is where agents share intermediate results and contextual information.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class MemoryEntry:
    key:        str
    value:      str
    owner_id:   str
    version:    int      = 1
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SharedMemory:

    def __init__(self):
        self._store: dict[str, MemoryEntry] = {}

    def read(self, key: str) -> MemoryEntry | None:
        return self._store.get(key)

    def write(self, key: str, value: str, writer_id: str) -> None:
        existing = self._store.get(key)
        if existing:
            existing.value     = value
            existing.version  += 1
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self._store[key] = MemoryEntry(key=key, value=value, owner_id=writer_id)

    def get_all(self) -> dict[str, MemoryEntry]:
        return dict(self._store)

    def summary(self) -> str:
        if not self._store:
            return "  (empty)"
        return "\n".join(
            f"  [{k}] (v{v.version}): {v.value[:80]}"
            for k, v in self._store.items()
        )
