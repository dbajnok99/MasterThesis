from dataclasses import dataclass

from langchain_core.tools import StructuredTool

from .canary import CanaryDefense
from .intent_anchor import IntentAnchorDefense
from .plan_diff import PlanDiffDefense
from .trust import TrustHierarchyDefense


@dataclass
class DefenseConfig:
    canary: CanaryDefense | None = None
    intent_anchor: IntentAnchorDefense | None = None
    plan_diff: PlanDiffDefense | None = None
    spotlight: bool = False
    trust: TrustHierarchyDefense | None = None


def build(names: list[str], model: str | None = None) -> DefenseConfig:
    return DefenseConfig(
        canary=CanaryDefense()                      if "canary"        in names else None,
        intent_anchor=IntentAnchorDefense(model)    if "intent-anchor" in names else None,
        plan_diff=PlanDiffDefense(model)            if "plan-diff"     in names else None,
        spotlight="spotlight"                       in names,
        trust=TrustHierarchyDefense()               if "trust"         in names else None,
    )


def spotlight_tools(tools: list) -> list:
    """Wrap each tool so its output is enclosed in <data> tags.

    This prevents the LLM from treating tool results as instructions.
    The agent system prompts must tell the LLM to treat <data> content
    as raw data only.
    """
    wrapped = []
    for t in tools:
        original = t.func

        def _make_wrapper(fn):
            def wrapper(*args, **kwargs):
                return f"<data>{fn(*args, **kwargs)}</data>"
            return wrapper

        wrapped.append(StructuredTool.from_function(
            func=_make_wrapper(original),
            name=t.name,
            description=t.description,
            args_schema=t.args_schema,
        ))
    return wrapped
