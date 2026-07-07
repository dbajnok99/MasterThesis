from .memory import SharedMemory
from .logger import AgentLogger
from .defenses import build as build_defenses
from .agents.mcp_tool_agent import MCPToolAgent
from .agents.fs_agent import FSAgent
from .agents.planner import PlannerAgent


class Orchestrator:

    def __init__(self, verbose: bool = True, defenses: list[str] | None = None,
                 model: str | None = None):
        self.logger  = AgentLogger(verbose=verbose)
        self.memory  = SharedMemory(logger=self.logger)
        self.history: list[dict] = []

        cfg = build_defenses(defenses, model=model) if defenses else None

        self.mcp_agent = MCPToolAgent(
            agent_id      = "mcp_agent",
            shared_memory = self.memory,
            logger        = self.logger,
            defenses      = cfg,
            model         = model,
        )
        self.fs_agent = FSAgent(
            agent_id      = "fs_agent",
            shared_memory = self.memory,
            logger        = self.logger,
            defenses      = cfg,
            model         = model,
        )
        self.planner = PlannerAgent(
            agent_id      = "planner",
            shared_memory = self.memory,
            logger        = self.logger,
            mcp_agent     = self.mcp_agent,
            fs_agent      = self.fs_agent,
            defenses      = cfg,
            model         = model,
        )

        if cfg and cfg.canary:
            cfg.canary.inject(self.memory)

        self._defenses = cfg

    def run(self, task: str) -> str:
        result = self.planner.process(task, history=self.history)
        self.history.append({"role": "user",      "content": task})
        self.history.append({"role": "assistant",  "content": result})

        if self._defenses and self._defenses.canary:
            tool_calls = self.mcp_agent.tool_calls + self.fs_agent.tool_calls
            hits = self._defenses.canary.check_run(result, tool_calls)
            if hits:
                self.logger.defense_canary_hit("orchestrator", hits)

        return result
