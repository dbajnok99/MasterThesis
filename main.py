"""
CLI entry point for the Multi-Agent System.

Usage:
  python main.py run "summarise the sandbox files"
  python main.py run "..." --log logs/run.json

  python main.py chat
  python main.py chat --log logs/session.jsonl
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from mas.orchestrator import Orchestrator


# ── Logging helpers ────────────────────────────────────────────────────────────

def _snapshot(orch: Orchestrator, task: str, result: str) -> dict:
    """Serialise one task's full execution state."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task":      task,
        "result":    result,
        "messages": [
            {
                "sender":   m.sender_id,
                "receiver": m.receiver_id,
                "type":     m.msg_type.value,
                "content":  m.content,
            }
            for m in orch.bus.log
        ],
        "tool_calls": list(orch.tool_agent.tool_calls),
        "memory": {
            k: {"value": v.value, "version": v.version, "owner": v.owner_id}
            for k, v in orch.memory.get_all().items()
        },
    }


def _save(path: Path, data: dict, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if append:
        with path.open("a") as f:
            f.write(json.dumps(data) + "\n")
    else:
        path.write_text(json.dumps(data, indent=2))


def _clear_run_state(orch: Orchestrator) -> None:
    orch.bus.log.clear()
    orch.tool_agent.tool_calls.clear()


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_run(args) -> None:
    orch   = Orchestrator()
    task   = args.task
    log    = Path(args.log) if args.log else None

    print(f"\nTask: {task}\n{'─' * 60}")
    result = orch.run(task)
    print(result)

    if log:
        snap = _snapshot(orch, task, result)
        _save(log, snap)
        print(f"\n[log saved → {log}]")


def cmd_chat(args) -> None:
    orch = Orchestrator()
    log  = Path(args.log) if args.log else None

    print("Multi-Agent System — chat mode  (type 'exit' or Ctrl-C to quit)\n")

    while True:
        try:
            task = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not task:
            continue
        if task.lower() in {"exit", "quit"}:
            break

        _clear_run_state(orch)
        result = orch.run(task)
        print(f"\nMAS: {result}\n")

        if log:
            snap = _snapshot(orch, task, result)
            _save(log, snap, append=True)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Multi-Agent System CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Execute a single task")
    p_run.add_argument("task", help="Task description")
    p_run.add_argument("--log", metavar="FILE", help="Save run log to JSON file")

    # chat
    p_chat = sub.add_parser("chat", help="Interactive chat session")
    p_chat.add_argument("--log", metavar="FILE", help="Append each turn to JSONL file")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "chat":
        cmd_chat(args)


if __name__ == "__main__":
    main()
