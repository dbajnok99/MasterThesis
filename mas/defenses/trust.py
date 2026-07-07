"""
Trust hierarchy defense.

Give every shared-memory entry a trust level based on where it came from (which
agent wrote it and what kind of data it is). The planner is only allowed to plan
from higher-trust entries; low-trust ones (file contents, or entries from an
unknown writer) are hidden from it, and the worker agents see them wrapped as
<untrusted> data.

This puts the trust order from Section 2.3.2 into the system itself, instead of
hoping the model respects it: a malicious instruction sitting in shared memory
can never turn into a plan step.
"""
from __future__ import annotations

# Trust levels, highest to lowest.
SYSTEM      = 3   # the planner's own plan or result
AGENT       = 2   # a worker agent's own result (a calculation, a write confirmation)
TOOL        = 1   # output from a tool (weather, stock)
ENVIRONMENT = 0   # file contents, or an entry from an unknown / pre-planted writer

_INTERNAL_AGENTS = {"planner", "fs_agent", "mcp_agent"}


def trust_of(owner_id: str, key: str) -> int:
    """Work out an entry's trust level from who wrote it and what it holds."""
    if owner_id == "planner":
        return SYSTEM
    if owner_id in _INTERNAL_AGENTS:
        if key.startswith("file_content:"):
            return ENVIRONMENT          # file contents can be controlled by an attacker
        if key.startswith("weather:") or key.startswith("stock:"):
            return TOOL
        return AGENT                    # write confirmations, calculations, listings
    return ENVIRONMENT                  # unknown writer, e.g. an injected poison entry


class TrustHierarchyDefense:
    """Filters the shared memory an agent sees, by trust level."""

    # The planner may only plan from entries at this level or above. Anything
    # lower (file contents, or an unknown writer) is hidden, so an injected
    # instruction never reaches the plan.
    PLANNER_MIN_TRUST = TOOL

    def context_lines(self, agent_id: str, entries: dict) -> list[str]:
        """Return the memory lines this agent is allowed to see."""
        lines: list[str] = []
        for key, entry in entries.items():
            level = trust_of(entry.owner_id, key)
            if agent_id == "planner" and level < self.PLANNER_MIN_TRUST:
                continue                # hide low-trust entries from the planner
            if level <= ENVIRONMENT:
                lines.append(
                    f"  [{key}] (trust: environment, owner: {entry.owner_id}): "
                    f"<untrusted>{entry.value}</untrusted>"
                )
            else:
                lines.append(f"  [{key}] (owner: {entry.owner_id}): {entry.value}")
        return lines
