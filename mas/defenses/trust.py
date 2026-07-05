"""
Trust hierarchy defense: label each shared-memory entry with a trust level
derived from its provenance (which agent wrote it and what kind of data it
holds), then keep low-trust content out of the planner's decomposition context
and mark it as untrusted, data-only for the worker agents.

This enforces the trust ordering from Section 2.3.2 in the architecture itself
instead of relying on the model to respect it: the planner never decomposes from
environment-derived or unrecognized entries, so an injected directive sitting in
shared memory cannot become a plan step.
"""
from __future__ import annotations

# Trust levels, highest to lowest (the Section 2.3.2 hierarchy).
SYSTEM      = 3   # the planner's own plan / synthesis
AGENT       = 2   # a worker agent's computed result (calculation, write confirmation)
TOOL        = 1   # output of an external tool (weather, stock)
ENVIRONMENT = 0   # file contents, or any entry from an unrecognized / pre-planted writer

_INTERNAL_AGENTS = {"planner", "fs_agent", "mcp_agent"}


def trust_of(owner_id: str, key: str) -> int:
    """Derive an entry's trust level from who wrote it and what it holds."""
    if owner_id == "planner":
        return SYSTEM
    if owner_id in _INTERNAL_AGENTS:
        if key.startswith("file_content:"):
            return ENVIRONMENT          # raw file bytes are attacker-controllable
        if key.startswith("weather:") or key.startswith("stock:"):
            return TOOL
        return AGENT                    # write confirmations, calculations, listings
    return ENVIRONMENT                  # unknown / pre-planted writer (e.g. injected poison)


class TrustHierarchyDefense:
    """Filters an agent's shared-memory context by entry trust level."""

    # The planner only decomposes from entries at or above this level; anything
    # lower (environment-derived or unrecognized) is withheld so injected
    # directives never reach the plan.
    PLANNER_MIN_TRUST = TOOL

    def context_lines(self, agent_id: str, entries: dict) -> list[str]:
        """Return the memory-context lines this agent is allowed to see."""
        lines: list[str] = []
        for key, entry in entries.items():
            level = trust_of(entry.owner_id, key)
            if agent_id == "planner" and level < self.PLANNER_MIN_TRUST:
                continue                # withhold low-trust content from planning
            if level <= ENVIRONMENT:
                lines.append(
                    f"  [{key}] (trust: environment, owner: {entry.owner_id}): "
                    f"<untrusted>{entry.value}</untrusted>"
                )
            else:
                lines.append(f"  [{key}] (owner: {entry.owner_id}): {entry.value}")
        return lines
