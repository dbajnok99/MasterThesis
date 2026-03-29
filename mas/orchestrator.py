from .memory import SharedMemory
from .message_bus import MessageBus
from .agents.mcp_tool_agent import MCPToolAgent
from .agents.fs_agent import FSAgent
from .agents.planner import PlannerAgent


class Orchestrator:

    def __init__(self):
        self.memory  = SharedMemory()
        self.bus     = MessageBus()
        self.history: list[dict] = []

        self.mcp_agent = MCPToolAgent(
            agent_id      = "mcp_agent",
            message_bus   = self.bus,
            shared_memory = self.memory,
        )
        self.fs_agent = FSAgent(
            agent_id      = "fs_agent",
            message_bus   = self.bus,
            shared_memory = self.memory,
        )
        self.planner = PlannerAgent(
            agent_id      = "planner",
            message_bus   = self.bus,
            shared_memory = self.memory,
            mcp_agent     = self.mcp_agent,
            fs_agent      = self.fs_agent,
        )

    def run(self, task: str) -> str:
        result = self.planner.process(task, history=self.history)
        self.history.append({"role": "user",      "content": task})
        self.history.append({"role": "assistant",  "content": result})
        return result
