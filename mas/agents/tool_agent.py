"""
Tool Agent

Uses LangChain's create_agent (backed by LangGraph) to run an agentic loop:
the LLM decides which tools to call, LangChain executes them, and the loop
continues until the LLM stops requesting tools.
"""
from __future__ import annotations

import config as cfg
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from ..agent import BaseAgent
from ..message import MessageType
from ..tools import ALL_TOOLS

SYSTEM = """\
You are a tool execution agent in a multi-agent system.
Use the available tools to complete the given subtask, then provide a concise answer.
"""


class ToolAgent(BaseAgent):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tool_calls: list[dict] = []

        llm = ChatOpenAI(
            model=cfg.MODEL,
            api_key=cfg.OPENAI_API_KEY,
            max_tokens=cfg.MAX_TOKENS,
        )
        self._graph = create_agent(llm, tools=ALL_TOOLS, system_prompt=SYSTEM)

    def process(self, task: str) -> str:
        # Do NOT clear here — accumulate across subtask calls within a single
        # top-level run.  The app layer clears tool_calls before each /api/run.

        # Stream the graph state; each chunk has the full messages list
        final_text = ""
        # Keep a map from tool_call_id → tool_name for pairing with ToolMessages
        pending: dict[str, dict] = {}   # call_id → {"tool": name, "args": args}

        for chunk in self._graph.stream(
            {"messages": [HumanMessage(task)]},
            stream_mode="values",
        ):
            last = chunk["messages"][-1]

            if isinstance(last, AIMessage) and last.tool_calls:
                for tc in last.tool_calls:
                    pending[tc["id"]] = {"tool": tc["name"], "args": tc["args"]}

            elif isinstance(last, ToolMessage):
                info = pending.pop(last.tool_call_id, {})
                if info:
                    self.tool_calls.append({
                        "tool":   info["tool"],
                        "args":   info["args"],
                        "output": last.content,
                    })

            elif isinstance(last, AIMessage) and last.content:
                final_text = last.content

        self.send(
            receiver_id = "planner",
            content     = final_text,
            msg_type    = MessageType.RESULT,
        )
        return final_text
