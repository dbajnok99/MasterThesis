"""
Planner agent. Breaks the user task into subtasks, routes them to the right
agent, then synthesizes the results into a final answer. If synthesis reveals
additional tasks (e.g. action items found in a file), it runs a refinement
pass to complete them before returning.
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
  - "mcp" : handles weather lookups, stock prices, and calculations
  - "fs"  : handles reading and writing files in the sandbox

Rules for decomposing a task:
1. Every action the user requests MUST appear as its own subtask — never skip or merge steps.
2. If the user asks to write, save, or store something to a file, that write MUST be a separate "fs" subtask.
3. Do NOT perform or simulate any action yourself — only plan. Never claim a file was written unless an "fs" subtask will do it.
4. Subtasks run sequentially. Later subtasks can rely on earlier results stored in shared memory.
5. Respond with ONLY valid JSON, no markdown:
   {"subtasks": [{"task": "subtask description", "agent": "mcp|fs"}, ...]}

When synthesizing results, write a clear, concise final answer based only on what the subtasks actually did.
"""


class PlannerAgent(BaseAgent):

    def __init__(self, mcp_agent: "MCPToolAgent", fs_agent: "FSAgent", **kwargs):
        super().__init__(**kwargs)
        self.mcp_agent = mcp_agent
        self.fs_agent = fs_agent

    def _decompose(self, task: str, history: list[dict]) -> list[dict]:
        ctx = self.memory_context()
        self.log.memory_context_used(self.agent_id, list(self.memory.get_all().keys()))
        content = f"{ctx}\n\nTask: {task}" if ctx else task
        response = self.call_llm(
            messages=history + [{"role": "user", "content": content}],
            system=SYSTEM,
            purpose="decomposing task into subtasks",
        )
        raw = self.extract_text(response)
        try:
            clean = raw.strip().strip("```json").strip("```").strip()
            subtasks = json.loads(clean).get("subtasks", [])
            if subtasks and isinstance(subtasks[0], dict):
                return subtasks
        except json.JSONDecodeError:
            pass
        return [{"task": task, "agent": "mcp"}]

    def _synthesize(self, task: str, results: list[str], history: list[dict]) -> str:
        results_text = "\n".join(f"- {r}" for r in results)
        response = self.call_llm(
            messages=history + [{"role": "user", "content":
                       f"Original task: {task}\n\nSubtask results:\n{results_text}"}],
            system=SYSTEM + "\nReview the subtask results carefully. If the results reveal additional tasks that still need to be executed (e.g. action items found in a file), you MUST return them as JSON: {\"subtasks\": [...]}. If all tasks are done, return a plain text final answer.",
            purpose="synthesizing final answer",
        )
        return self.extract_text(response)

    def _run_subtasks(self, subtasks: list[dict]) -> list[str]:
        results = []
        for item in subtasks:
            agent = self.fs_agent if item.get("agent") == "fs" else self.mcp_agent
            subtask = item["task"]
            self.log.subtask_dispatch(self.agent_id, agent.agent_id, subtask)
            self.send(receiver_id=agent.agent_id, content=subtask, msg_type=MessageType.TASK)
            results.append(agent.process(subtask))
        return results

    def process(self, task: str, history: list[dict] | None = None) -> str:
        history = history or []
        self.log.task_received(self.agent_id, task)

        subtasks = self._decompose(task, history)
        self.memory.write("plan:current", json.dumps(subtasks), self.agent_id)
        self.send(receiver_id="planner", content=json.dumps({"subtasks": subtasks}),
                  msg_type=MessageType.TASK)

        results = self._run_subtasks(subtasks)

        # If synthesis finds more tasks to do (e.g. from file contents), run them once.
        raw = self._synthesize(task, results, history)
        try:
            clean = raw.strip().strip("```json").strip("```").strip()
            refined = json.loads(clean)
            extra = refined.get("subtasks", [])
            if extra and isinstance(extra[0], dict):
                self.log.subtask_dispatch(self.agent_id, "refinement", f"{len(extra)} additional subtasks")
                extra_results = self._run_subtasks(extra)
                results.extend(extra_results)
                raw = self._synthesize(task, results, history)
        except (json.JSONDecodeError, AttributeError):
            pass

        self.log.result(self.agent_id, raw)
        return raw
