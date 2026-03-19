from .memory import SharedMemory
from .message_bus import MessageBus
from .agents.tool_agent import ToolAgent
from .agents.planner import PlannerAgent


class Orchestrator:

    def __init__(self):
        self.memory  = SharedMemory()
        self.bus     = MessageBus()
        self.history: list[dict] = []

        self.tool_agent = ToolAgent(
            agent_id      = "tool_agent",
            message_bus   = self.bus,
            shared_memory = self.memory,
        )
        self.planner = PlannerAgent(
            agent_id      = "planner",
            message_bus   = self.bus,
            shared_memory = self.memory,
            tool_agent    = self.tool_agent,
        )

    def run(self, task: str) -> str:
        result = self.planner.process(task, history=self.history)
        self.history.append({"role": "user",      "content": task})
        self.history.append({"role": "assistant",  "content": result})
        return result
