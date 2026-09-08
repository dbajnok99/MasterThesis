"""
Reconstructs cross-agent data flow from the logger's event stream, instead of
guessing propagation happened because the final artefact looks right.

Every subtask already logs `memory_write` (who wrote a key) and
`memory_context_used` (what keys an agent saw when it started). Walking that
timeline tells us when agent B saw a key agent A wrote, and whether B's own
tool calls afterward actually contain that value — i.e. B didn't just have
access to A's data, it used it.
"""
from __future__ import annotations

_SNIPPET_LEN = 40  # chars of a written value used to spot reuse downstream


def build_provenance(events: list[dict]) -> list[dict]:
    """Cross-agent read edges found in one run's events.

    Each edge: {"key", "writer", "reader", "write_index", "read_index",
    "value_snippet", "reused"}.
    """
    last_write: dict[str, tuple[str, int, str]] = {}  # key -> (writer, event_index, value)
    edges: list[dict] = []

    for i, ev in enumerate(events):
        et = ev.get("event")

        if et == "memory_write":
            key = ev.get("key")
            if key is not None:
                last_write[key] = (ev.get("agent"), i, ev.get("value") or "")

        elif et == "memory_context_used":
            reader = ev.get("agent")
            for key in ev.get("keys", []):
                w = last_write.get(key)
                if not w:
                    continue
                writer, write_index, value = w
                if writer == reader or write_index >= i:
                    continue
                edges.append({
                    "key":           key,
                    "writer":        writer,
                    "reader":        reader,
                    "write_index":   write_index,
                    "read_index":    i,
                    "value_snippet": value[:_SNIPPET_LEN],
                    "reused":        _reused_later(events, i, reader, value),
                })

    return edges


def _reused_later(events: list[dict], from_index: int, agent: str, value: str) -> bool:
    needle = value.strip()[:_SNIPPET_LEN]
    if not needle:
        return False
    for ev in events[from_index + 1:]:
        if ev.get("agent") != agent:
            continue
        et = ev.get("event")
        if et == "tool_call" and needle in str(ev.get("args", "")):
            return True
        if et == "tool_result" and needle in str(ev.get("output", "")):
            return True
        if et == "result" and needle in str(ev.get("value", "")):
            return True
    return False


def propagation_edges(events: list[dict]) -> list[dict]:
    """Edges where data actually crossed agents and got acted on."""
    return [e for e in build_provenance(events) if e["reused"]]
