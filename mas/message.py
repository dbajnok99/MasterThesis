from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class MessageType(str, Enum):
    TASK   = "task"    # Orchestrator/Planner → agent
    RESULT = "result"  # Agent → Planner/Orchestrator


@dataclass
class Message:
    sender_id:   str
    receiver_id: str
    content:     str
    msg_type:    MessageType
    msg_id:      str      = field(default_factory=lambda: uuid.uuid4().hex)
    parent_id:   str | None = None
    metadata:    dict     = field(default_factory=dict)
    timestamp:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))
