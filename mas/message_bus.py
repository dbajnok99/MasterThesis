"""
Message bus — routes messages between agents and keeps an audit log.
"""
from __future__ import annotations

from typing import Callable
from .message import Message

Subscriber = Callable[[Message], None]


class MessageBus:

    def __init__(self):
        self._subscribers: dict[str, Subscriber] = {}
        self.log: list[Message] = []

    def register(self, agent_id: str, handler: Subscriber) -> None:
        self._subscribers[agent_id] = handler

    def send(self, message: Message) -> None:
        self.log.append(message)
        handler = self._subscribers.get(message.receiver_id)
        if handler:
            handler(message)
