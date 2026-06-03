from . import (
    indirect_injection,
    cross_agent_propagation,
    memory_poison,
    planner_hijack,
    system_prompt_extraction,
    memory_membership_probe,
    tool_result_poisoning,
)

ALL_ATTACKS = {
    "indirect_injection":       indirect_injection,
    "cross_agent_propagation":  cross_agent_propagation,
    "memory_poison":            memory_poison,
    "planner_hijack":           planner_hijack,
    "system_prompt_extraction": system_prompt_extraction,
    "memory_membership_probe":  memory_membership_probe,
    "tool_result_poisoning":    tool_result_poisoning,
}
