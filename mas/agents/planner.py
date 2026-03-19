"""
Planner Agent

1. Reads shared memory for context.
2. Calls the LLM to decompose the task into subtasks.
3. Sends each subtask to the ToolAgent and collects results.
4. Calls the LLM again to synthesize a final answer.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..agent import BaseAgent
from ..message import MessageType

if TYPE_CHECKING:
    from .tool_agent import ToolAgent

SYSTEM = """\
You are a planning agent in a multi-agent system.

When decomposing a task, respond with ONLY valid JSON:
{"subtasks": ["subtask 1", "subtask 2", ...]}

When synthesizing results, write a clear, concise final answer.
"""


class PlannerAgent(BaseAgent):

    def __init__(self, tool_agent: "ToolAgent", **kwargs):
        super().__init__(**kwargs)
        self.tool_agent = tool_agent

    def _memory_context(self) -> str:
        entries = self.memory.get_all()
        if not entries:
            return ""
        lines = ["Shared memory:"]
        for key, entry in entries.items():
            lines.append(f"  [{key}]: {entry.value}")
        return "\n".join(lines)

    def _decompose(self, task: str, history: list[dict]) -> list[str]:
        ctx     = self._memory_context()
        content = f"{ctx}\n\nTask: {task}" if ctx else task
        response = self.call_llm(
            messages=history + [{"role": "user", "content": content}],
            system=SYSTEM,
        )
        raw = self.extract_text(response)
        try:
            clean = raw.strip().strip("```json").strip("```").strip()
            return json.loads(clean).get("subtasks", [task])
        except json.JSONDecodeError:
            return [task]

    def _synthesize(self, task: str, results: list[str], history: list[dict]) -> str:
        results_text = "\n".join(f"- {r}" for r in results)
        response = self.call_llm(
            messages=history + [{"role": "user", "content":
                       f"Original task: {task}\n\nSubtask results:\n{results_text}"}],
            system=SYSTEM + "\nYou are now synthesizing the results into a final answer.",
        )
        return self.extract_text(response)

    def process(self, task: str, history: list[dict] | None = None) -> str:
        history = history or []
        subtasks = self._decompose(task, history)

        # Log decomposition on the bus
        self.send(
            receiver_id = self.tool_agent.agent_id,
            content     = json.dumps({"subtasks": subtasks}),
            msg_type    = MessageType.TASK,
        )

        # Execute each subtask
        results = [self.tool_agent.process(subtask) for subtask in subtasks]

        return self._synthesize(task, results, history)
