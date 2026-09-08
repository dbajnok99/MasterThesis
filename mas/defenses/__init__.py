from dataclasses import dataclass

from .canary import CanaryDefense
from .intent_anchor import IntentAnchorDefense
from .plan_diff import PlanDiffDefense
from .spotlight import spotlight_tools
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
