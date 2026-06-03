"""Base class for all agents in the system."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import config as cfg
from .llm import make_raw_client
from .message import Message, MessageType
from .memory import SharedMemory
from .logger import AgentLogger

if TYPE_CHECKING:
    from .message_bus import MessageBus
    from .defenses import DefenseConfig


class BaseAgent(ABC):

    def __init__(self, agent_id: str, message_bus: "MessageBus",
                 shared_memory: SharedMemory, logger: AgentLogger | None = None,
                 defenses: "DefenseConfig | None" = None,
                 model: str | None = None):
        self.agent_id = agent_id
        self.bus = message_bus
        self.memory = shared_memory
        self.log = logger or AgentLogger(verbose=False)
        self.defenses = defenses
        self._model = model or cfg.MODEL
        self._client = make_raw_client(self._model)

    def send(self, receiver_id: str, content: str,
             msg_type: MessageType, metadata: dict | None = None) -> None:
        # Agents coordinate through shared memory; this only records the
        # dispatch in the bus audit log for later inspection.
        msg = Message(
            sender_id=self.agent_id,
            receiver_id=receiver_id,
            content=content,
            msg_type=msg_type,
            metadata=metadata or {},
        )
        self.bus.send(msg)

    def call_llm(self, messages: list[dict], system: str = "",
                 tools: list[dict] | None = None, purpose: str = "") -> str:
        if purpose:
            self.log.llm_call(self.agent_id, purpose)
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        return self._client.complete(full_messages)

    def memory_context(self) -> str:
        entries = self.memory.get_all()
        if not entries:
            return ""
        spotlight = self.defenses and self.defenses.spotlight
        lines = ["Shared memory (results from prior subtasks):"]
        for key, entry in entries.items():
            if spotlight:
                lines.append(f"  [{key}]: <data>{entry.value}</data>")
            else:
                lines.append(f"  [{key}] (owner: {entry.owner_id}): {entry.value}")
        return "\n".join(lines)

    @abstractmethod
    def process(self, task: str) -> str:
        ...
