"""Keeps an ordered audit log of every message agents dispatch."""
from __future__ import annotations

from .message import Message


class MessageBus:

    def __init__(self):
        self.log: list[Message] = []

    def send(self, message: Message) -> None:
        self.log.append(message)
