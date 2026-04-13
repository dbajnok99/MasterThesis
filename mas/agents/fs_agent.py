"""File system agent. Handles reading and writing files in the sandbox."""
from __future__ import annotations

import config as cfg
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from ..agent import BaseAgent
from ..message import MessageType
from ..tools import FS_TOOLS

SYSTEM = """\
You are a file system agent in a multi-agent system.
Use the available tools to read and write files in the sandbox workspace,
then provide a concise answer.
"""


class FSAgent(BaseAgent):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tool_calls: list[dict] = []

        llm = ChatOpenAI(
            model=cfg.MODEL,
            api_key=cfg.OPENAI_API_KEY,
            max_tokens=cfg.MAX_TOKENS,
        )
        self._graph = create_agent(llm, tools=FS_TOOLS, system_prompt=SYSTEM)

    @staticmethod
    def _memory_key(tool: str, args: dict) -> str:
        if tool == "file_write":
            return f"file:{args.get('path', 'unknown')}"
        if tool == "file_read":
            return f"file_content:{args.get('path', 'unknown')}"
        if tool == "list_files":
            return "files:list"
        return tool

    def process(self, task: str) -> str:
        self.log.task_received(self.agent_id, task)

        ctx = self.memory_context()
        self.log.memory_context_used(self.agent_id, list(self.memory.get_all().keys()))
        full_task = f"{ctx}\n\nTask: {task}" if ctx else task

        self.log.llm_call(self.agent_id, "executing subtask")

        final_text = ""
        pending: dict[str, dict] = {}

        for chunk in self._graph.stream(
            {"messages": [HumanMessage(full_task)]},
            stream_mode="values",
        ):
            last = chunk["messages"][-1]

            if isinstance(last, AIMessage) and last.tool_calls:
                reasoning = last.content or ""
                for tc in last.tool_calls:
                    self.log.tool_call(self.agent_id, tc["name"], tc["args"])
                    pending[tc["id"]] = {"tool": tc["name"], "args": tc["args"], "reasoning": reasoning}

            elif isinstance(last, ToolMessage):
                info = pending.pop(last.tool_call_id, {})
                if info:
                    self.log.tool_result(self.agent_id, info["tool"], last.content)
                    mem_key = self._memory_key(info["tool"], info["args"])
                    self.memory.write(mem_key, last.content, self.agent_id)
                    entry = {"tool": info["tool"], "args": info["args"], "output": last.content}
                    if info.get("reasoning"):
                        entry["reasoning"] = info["reasoning"]
                    self.tool_calls.append(entry)

            elif isinstance(last, AIMessage) and last.content:
                final_text = last.content

        self.log.result(self.agent_id, final_text)
        self.send(receiver_id="planner", content=final_text, msg_type=MessageType.RESULT)
        return final_text
