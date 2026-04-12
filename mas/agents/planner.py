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
        self.fs_agent  = fs_agent

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
            purpose="synthesizing final answer",
        )
        return self.extract_text(response)

    def process(self, task: str, history: list[dict] | None = None) -> str:
        history  = history or []
        self.log.task_received(self.agent_id, task)

        subtasks = self._decompose(task, history)

        # Persist the plan so agents and future calls have full visibility
        self.memory.write("plan:current", json.dumps(subtasks), self.agent_id)

        # Log decomposition on the bus
        self.send(
            receiver_id = "planner",
            content     = json.dumps({"subtasks": subtasks}),
            msg_type    = MessageType.TASK,
        )

        # Route each subtask; each agent reads shared memory for prior context itself
        results = []
        for item in subtasks:
            agent_key = item.get("agent", "mcp")
            agent     = self.fs_agent if agent_key == "fs" else self.mcp_agent
            subtask   = item["task"]

            self.log.subtask_dispatch(self.agent_id, agent.agent_id, subtask)
            self.send(
                receiver_id = agent.agent_id,
                content     = subtask,
                msg_type    = MessageType.TASK,
            )
            results.append(agent.process(subtask))

        final = self._synthesize(task, results, history)
        self.log.result(self.agent_id, final)
        return final
