"""
MCP Tool Agent

Handles stateless external/computation tools: weather, stock prices, calculations.
"""
from __future__ import annotations

import config as cfg
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from ..agent import BaseAgent
from ..message import MessageType
from ..tools import MCP_TOOLS

SYSTEM = """\
You are an MCP tool agent in a multi-agent system.
Use the available tools (weather, stock prices, calculations) to complete the given subtask,
then provide a concise answer.
"""


class MCPToolAgent(BaseAgent):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tool_calls: list[dict] = []

        llm = ChatOpenAI(
            model=cfg.MODEL,
            api_key=cfg.OPENAI_API_KEY,
            max_tokens=cfg.MAX_TOKENS,
        )
        self._graph = create_agent(llm, tools=MCP_TOOLS, system_prompt=SYSTEM)

    def process(self, task: str) -> str:
        final_text = ""
        pending: dict[str, dict] = {}

        for chunk in self._graph.stream(
            {"messages": [HumanMessage(task)]},
            stream_mode="values",
        ):
            last = chunk["messages"][-1]

            if isinstance(last, AIMessage) and last.tool_calls:
                reasoning = last.content or ""
                for tc in last.tool_calls:
                    pending[tc["id"]] = {"tool": tc["name"], "args": tc["args"], "reasoning": reasoning}

            elif isinstance(last, ToolMessage):
                info = pending.pop(last.tool_call_id, {})
                if info:
                    entry = {"tool": info["tool"], "args": info["args"], "output": last.content}
                    if info.get("reasoning"):
                        entry["reasoning"] = info["reasoning"]
                    self.tool_calls.append(entry)

            elif isinstance(last, AIMessage) and last.content:
                final_text = last.content

        self.send(
            receiver_id = "planner",
            content     = final_text,
            msg_type    = MessageType.RESULT,
        )
        return final_text
