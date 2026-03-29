"""
Planner Agent

1. Reads shared memory for context.
2. Calls the LLM to decompose the task into subtasks, each tagged with a target agent.
3. Routes each subtask to either the MCPToolAgent or the FSAgent and collects results.
4. Calls the LLM again to synthesize a final answer.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..agent import BaseAgent
from ..message import MessageType

if TYPE_CHECKING:
    from .mcp_tool_agent import MCPToolAgent
    from .fs_agent import FSAgent

SYSTEM = """\
You are a planning agent in a multi-agent system.

You have two specialist agents available:
  - "mcp"  : handles weather lookups, stock prices, and calculations
  - "fs"   : handles reading and writing files in the sandbox

When decomposing a task, respond with ONLY valid JSON:
{"subtasks": [{"task": "subtask description", "agent": "mcp|fs"}, ...]}

When synthesizing results, write a clear, concise final answer.
"""


class PlannerAgent(BaseAgent):

    def __init__(self, mcp_agent: "MCPToolAgent", fs_agent: "FSAgent", **kwargs):
        super().__init__(**kwargs)
        self.mcp_agent = mcp_agent
        self.fs_agent  = fs_agent

    def _memory_context(self) -> str:
        entries = self.memory.get_all()
        if not entries:
            return ""
        lines = ["Shared memory:"]
        for key, entry in entries.items():
            lines.append(f"  [{key}]: {entry.value}")
        return "\n".join(lines)

    def _decompose(self, task: str, history: list[dict]) -> list[dict]:
        ctx     = self._memory_context()
        content = f"{ctx}\n\nTask: {task}" if ctx else task
        response = self.call_llm(
            messages=history + [{"role": "user", "content": content}],
            system=SYSTEM,
        )
        raw = self.extract_text(response)
        try:
            clean = raw.strip().strip("```json").strip("```").strip()
            subtasks = json.loads(clean).get("subtasks", [])
            # Fallback: if parsing succeeds but subtasks is empty or malformed
            if subtasks and isinstance(subtasks[0], dict):
                return subtasks
        except json.JSONDecodeError:
            pass
        # Fallback: send the whole task to mcp by default
        return [{"task": task, "agent": "mcp"}]

    def _synthesize(self, task: str, results: list[str], history: list[dict]) -> str:
        results_text = "\n".join(f"- {r}" for r in results)
        response = self.call_llm(
            messages=history + [{"role": "user", "content":
                       f"Original task: {task}\n\nSubtask results:\n{results_text}"}],
            system=SYSTEM + "\nYou are now synthesizing the results into a final answer.",
        )
        return self.extract_text(response)

    def process(self, task: str, history: list[dict] | None = None) -> str:
        history  = history or []
        subtasks = self._decompose(task, history)

        # Log decomposition on the bus
        self.send(
            receiver_id = "planner",
            content     = json.dumps({"subtasks": subtasks}),
            msg_type    = MessageType.TASK,
        )

        # Route each subtask to the appropriate agent
        results = []
        for item in subtasks:
            agent_key = item.get("agent", "mcp")
            agent     = self.fs_agent if agent_key == "fs" else self.mcp_agent
            results.append(agent.process(item["task"]))

        return self._synthesize(task, results, history)
