"""
Timestamped, colour-coded stdout logger. Also accumulates structured events
so they can be included in the JSON log snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone

_AGENT_COLORS: dict[str, str] = {
    "planner":   "\033[94m",  # bright blue
    "mcp_agent": "\033[92m",  # bright green
    "fs_agent":  "\033[93m",  # bright yellow
}
_RESET = "\033[0m"
_DIM   = "\033[2m"


def _color(agent_id: str) -> str:
    return _AGENT_COLORS.get(agent_id, "\033[37m")


class AgentLogger:

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.events: list[dict] = []

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

    def _emit(self, agent_id: str, msg: str) -> None:
        if not self.verbose:
            return
        label = f"{_color(agent_id)}[{agent_id}]{_RESET}"
        print(f"  {_DIM}{self._ts()}{_RESET} {label} {msg}", flush=True)

    def _record(self, event: str, agent_id: str, **kw) -> None:
        self.events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "agent": agent_id,
            **kw,
        })

    def task_received(self, agent_id: str, task: str) -> None:
        self._record("task_received", agent_id, task=task)
        preview = task[:100].replace("\n", " ")
        self._emit(agent_id, f"task: {preview}{'...' if len(task) > 100 else ''}")

    def subtask_dispatch(self, agent_id: str, target: str, subtask: str) -> None:
        self._record("subtask_dispatch", agent_id, target=target, subtask=subtask)
        preview = subtask[:80].replace("\n", " ")
        self._emit(agent_id, f"dispatch -> [{target}]: {preview}{'...' if len(subtask) > 80 else ''}")

    def llm_call(self, agent_id: str, purpose: str) -> None:
        self._record("llm_call", agent_id, purpose=purpose)
        self._emit(agent_id, f"LLM call: {purpose}")

    def tool_call(self, agent_id: str, tool: str, args: dict) -> None:
        self._record("tool_call", agent_id, tool=tool, args=args)
        self._emit(agent_id, f"tool: {tool}({args})")

    def tool_result(self, agent_id: str, tool: str, output: str) -> None:
        self._record("tool_result", agent_id, tool=tool, output=output)
        preview = output[:80].replace("\n", " ")
        self._emit(agent_id, f"  [{tool}]: {preview}{'...' if len(output) > 80 else ''}")

    def memory_context_used(self, agent_id: str, keys: list[str]) -> None:
        self._record("memory_context_used", agent_id, keys=keys)
        self._emit(agent_id, f"memory scan  keys={keys}")

    def memory_write(self, agent_id: str, key: str, value: str) -> None:
        self._record("memory_write", agent_id, key=key, value=value)
        preview = value[:60].replace("\n", " ")
        self._emit(agent_id, f"memory[{key}] = {preview}{'...' if len(value) > 60 else ''}")

    def defense_anchor_set(self, agent_id: str, task: str, anchor: dict) -> None:
        self._record("defense_anchor_set", agent_id, task=task, anchor=anchor)
        self._emit(agent_id, f"\033[96m[intent_anchor] anchor set: {anchor}\033[0m")

    def defense_subtask_verified(self, agent_id: str, subtask: str, allowed: bool) -> None:
        self._record("defense_subtask_verified", agent_id, subtask=subtask, allowed=allowed)
        verdict = "\033[92mALLOWED\033[0m" if allowed else "\033[91mBLOCKED\033[0m"
        self._emit(agent_id, f"\033[96m[intent_anchor] {verdict}: {subtask[:80]}\033[0m")

    def defense_plan_diff(self, agent_id: str, removed: list[str]) -> None:
        self._record("defense_plan_diff", agent_id, removed=removed)
        self._emit(agent_id, f"\033[96m[plan_diff] removed {len(removed)} suspicious subtask(s): {removed}\033[0m")

    def defense_canary_hit(self, agent_id: str, triggered: list[str]) -> None:
        self._record("defense_canary_hit", agent_id, triggered=triggered)
        self._emit(agent_id, f"\033[91m[canary] exfiltration detected — triggered: {triggered}\033[0m")

    def result(self, agent_id: str, value: str) -> None:
        self._record("result", agent_id, value=value)
        preview = value[:100].replace("\n", " ")
        self._emit(agent_id, f"result: {preview}{'...' if len(value) > 100 else ''}")
