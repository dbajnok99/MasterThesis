"""
Base agent.

Every agent has:
  - an identity (agent_id)
  - access to shared memory and the message bus
  - a call_llm() helper that talks to the OpenAI API
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from openai import OpenAI

import config as cfg
from .message import Message, MessageType
from .memory import SharedMemory

if TYPE_CHECKING:
    from .message_bus import MessageBus


class BaseAgent(ABC):

    def __init__(
        self,
        agent_id:      str,
        message_bus:   "MessageBus",
        shared_memory: SharedMemory,
    ):
        self.agent_id = agent_id
        self.bus      = message_bus
        self.memory   = shared_memory
        self._client  = OpenAI(api_key=cfg.OPENAI_API_KEY)

        self.bus.register(agent_id, self._on_message)
        self._inbox: list[Message] = []

    # ── Bus integration ────────────────────────────────────────────────────

    def _on_message(self, msg: Message) -> None:
        self._inbox.append(msg)

    def send(self, receiver_id: str, content: str,
             msg_type: MessageType, metadata: dict | None = None) -> None:
        msg = Message(
            sender_id   = self.agent_id,
            receiver_id = receiver_id,
            content     = content,
            msg_type    = msg_type,
            metadata    = metadata or {},
        )
        self.bus.send(msg)

    # ── LLM helper ─────────────────────────────────────────────────────────

    def call_llm(self, messages: list[dict], system: str = "",
                 tools: list[dict] | None = None):
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict = dict(
            model      = cfg.MODEL,
            max_tokens = cfg.MAX_TOKENS,
            messages   = full_messages,
        )
        if tools:
            kwargs["tools"]       = tools
            kwargs["tool_choice"] = "auto"

        return self._client.chat.completions.create(**kwargs)

    @staticmethod
    def extract_text(response) -> str:
        return response.choices[0].message.content or ""

    # ── Entry point ────────────────────────────────────────────────────────

    @abstractmethod
    def process(self, task: str) -> str:
        ...
