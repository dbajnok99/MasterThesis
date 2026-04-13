"""Base class for all agents in the system."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from openai import OpenAI

import config as cfg
from .message import Message, MessageType
from .memory import SharedMemory
from .logger import AgentLogger

if TYPE_CHECKING:
    from .message_bus import MessageBus


class BaseAgent(ABC):

    def __init__(self, agent_id: str, message_bus: "MessageBus",
                 shared_memory: SharedMemory, logger: AgentLogger | None = None):
        self.agent_id = agent_id
        self.bus = message_bus
        self.memory = shared_memory
        self.log = logger or AgentLogger(verbose=False)
        self._client = OpenAI(api_key=cfg.OPENAI_API_KEY)

        self.bus.register(agent_id, self._on_message)
        self._inbox: list[Message] = []

    def _on_message(self, msg: Message) -> None:
        self._inbox.append(msg)

    def send(self, receiver_id: str, content: str,
             msg_type: MessageType, metadata: dict | None = None) -> None:
        msg = Message(
            sender_id=self.agent_id,
            receiver_id=receiver_id,
            content=content,
            msg_type=msg_type,
            metadata=metadata or {},
        )
        self.bus.send(msg)

    def call_llm(self, messages: list[dict], system: str = "",
                 tools: list[dict] | None = None, purpose: str = ""):
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        if purpose:
            self.log.llm_call(self.agent_id, purpose)

        kwargs: dict = dict(
            model=cfg.MODEL,
            max_tokens=cfg.MAX_TOKENS,
            messages=full_messages,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return self._client.chat.completions.create(**kwargs)

    @staticmethod
    def extract_text(response) -> str:
        return response.choices[0].message.content or ""

    def memory_context(self) -> str:
        """Build a string of all shared memory entries to inject into agent prompts."""
        entries = self.memory.get_all()
        if not entries:
            return ""
        lines = ["Shared memory (results from prior subtasks):"]
        for key, entry in entries.items():
            lines.append(f"  [{key}] (owner: {entry.owner_id}): {entry.value}")
        return "\n".join(lines)

    @abstractmethod
    def process(self, task: str) -> str:
        ...
