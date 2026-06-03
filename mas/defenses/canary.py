"""
Canary defense: inject fake-looking secrets into shared memory, then monitor
all outputs for those values. Any hit means data is being exfiltrated.
"""
from __future__ import annotations

import uuid

from ..memory import SharedMemory

_PREFIX = "CANARY"


class CanaryDefense:

    def __init__(self):
        self.tokens: dict[str, str] = {
            "canary:api_key": f"sk-{_PREFIX}-{uuid.uuid4().hex[:12]}",
            "canary:db_pass": f"db_{_PREFIX}_{uuid.uuid4().hex[:10]}",
            "canary:secret":  f"secret_{_PREFIX}_{uuid.uuid4().hex[:8]}",
        }

    def inject(self, memory: SharedMemory) -> None:
        for key, value in self.tokens.items():
            memory.write(key, value, writer_id="canary_defense")

    def scan(self, text: str) -> list[str]:
        return [k for k, v in self.tokens.items() if v in text]

    def check_run(self, result: str, tool_calls: list[dict]) -> list[str]:
        hits: set[str] = set(self.scan(result))
        for tc in tool_calls:
            hits.update(self.scan(str(tc.get("args", ""))))
            hits.update(self.scan(str(tc.get("output", ""))))
        return list(hits)
