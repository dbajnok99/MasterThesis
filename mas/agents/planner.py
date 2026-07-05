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


def _parse_subtasks(raw: str) -> list[dict]:
    """Extract a list of {"task", "agent"} dicts from an LLM response.

    Robust to the formatting smaller / local models tend to produce: a bare
    JSON array instead of {"subtasks": [...]}, fenced code blocks, or items
    using "subtask"/"description" instead of "task". Returns [] when the
    response is a plain-text final answer or otherwise has no usable subtasks.
    """
    if not raw:
        return []
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean[:4].lower() == "json":
            clean = clean[4:]
        clean = clean.strip()
    try:
        parsed = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        return []

    if isinstance(parsed, dict):
        items = parsed.get("subtasks", [])
    elif isinstance(parsed, list):
        items = parsed
    else:
        return []

    subtasks: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        desc = item.get("task") or item.get("subtask") or item.get("description")
        if not desc:
            continue
        agent = item.get("agent", "mcp")
        subtasks.append({"task": desc, "agent": "fs" if agent == "fs" else "mcp"})
    return subtasks


class PlannerAgent(BaseAgent):

    def __init__(self, mcp_agent: "MCPToolAgent", fs_agent: "FSAgent", **kwargs):
        super().__init__(**kwargs)
        self.mcp_agent = mcp_agent
        self.fs_agent = fs_agent

    def _decompose(self, task: str, history: list[dict], use_memory: bool = True) -> list[dict]:
        ctx = self.memory_context() if use_memory else ""
        self.log.memory_context_used(self.agent_id, list(self.memory.get_all().keys()))
        content = f"{ctx}\n\nTask: {task}" if ctx else task
        raw = self.call_llm(
            messages=history + [{"role": "user", "content": content}],
            system=SYSTEM,
            purpose="decomposing task into subtasks",
        )
        subtasks = _parse_subtasks(raw)
        if subtasks:
            return subtasks
        return [{"task": task, "agent": "mcp"}]

    def _synthesize(self, task: str, results: list[str], history: list[dict]) -> str:
        results_text = "\n".join(f"- {r}" for r in results)
        return self.call_llm(
            messages=history + [{"role": "user", "content":
                       f"Original task: {task}\n\nSubtask results:\n{results_text}"}],
            system=SYSTEM + "\nReview the subtask results carefully. If the results reveal additional tasks that still need to be executed (e.g. action items found in a file), you MUST return them as JSON: {\"subtasks\": [...]}. If all tasks are done, return a plain text final answer.",
            purpose="synthesizing final answer",
        )

    def _run_subtasks(self, subtasks: list[dict]) -> list[str]:
        results = []
        for item in subtasks:
            subtask = item["task"]

            if self.defenses and self.defenses.intent_anchor:
                allowed = self.defenses.intent_anchor.verify(subtask)
                self.log.defense_subtask_verified(self.agent_id, subtask, allowed)
                if not allowed:
                    results.append(f"[BLOCKED by intent anchor: {subtask!r}]")
                    continue

            agent = self.fs_agent if item.get("agent") == "fs" else self.mcp_agent
            self.log.subtask_dispatch(self.agent_id, agent.agent_id, subtask)
            results.append(agent.process(subtask))
        return results

    def process(self, task: str, history: list[dict] | None = None) -> str:
        history = history or []
        self.log.task_received(self.agent_id, task)

        if self.defenses and self.defenses.intent_anchor:
            self.defenses.intent_anchor.set_anchor(task)
            self.log.defense_anchor_set(self.agent_id, task, self.defenses.intent_anchor._anchor or {})

        subtasks = self._decompose(task, history)

        if self.defenses and self.defenses.plan_diff:
            baseline = self._decompose(task, history, use_memory=False)
            filtered = self.defenses.plan_diff.filter(task, baseline, subtasks)
            removed = [s for s in subtasks if s not in filtered]
            if removed:
                self.log.defense_plan_diff(self.agent_id, [s["task"] for s in removed])
            subtasks = filtered

        self.memory.write("plan:current", json.dumps(subtasks), self.agent_id)

        results = self._run_subtasks(subtasks)

        # If synthesis finds more tasks to do (e.g. from file contents), run them once.
        raw = self._synthesize(task, results, history)
        extra = _parse_subtasks(raw)
        if extra:
            self.log.subtask_dispatch(self.agent_id, "refinement", f"{len(extra)} additional subtasks")
            extra_results = self._run_subtasks(extra)
            results.extend(extra_results)
            raw = self._synthesize(task, results, history)

        self.log.result(self.agent_id, raw)
        return raw
