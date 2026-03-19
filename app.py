import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify
from mas.orchestrator import Orchestrator

app = Flask(__name__)

# One persistent orchestrator — memory accumulates across tasks (realistic).
orch = Orchestrator()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/run", methods=["POST"])
def api_run():
    task = request.json.get("task", "").strip()
    if not task:
        return jsonify({"error": "empty task"}), 400

    # Clear per-run state
    orch.bus.log.clear()
    orch.tool_agent.tool_calls.clear()

    result = orch.run(task)

    messages = [
        {
            "sender":   m.sender_id,
            "receiver": m.receiver_id,
            "type":     m.msg_type.value,
            "content":  m.content,
        }
        for m in orch.bus.log
    ]

    memory = {
        k: {"value": v.value, "version": v.version, "owner": v.owner_id}
        for k, v in orch.memory.get_all().items()
    }

    return jsonify({
        "result":     result,
        "messages":   messages,
        "memory":     memory,
        "tool_calls": orch.tool_agent.tool_calls,
    })


@app.route("/api/memory", methods=["GET"])
def api_memory_get():
    return jsonify({
        k: {"value": v.value, "version": v.version, "owner": v.owner_id}
        for k, v in orch.memory.get_all().items()
    })


@app.route("/api/memory", methods=["POST"])
def api_memory_set():
    key   = request.json.get("key", "").strip()
    value = request.json.get("value", "").strip()
    if not key:
        return jsonify({"error": "key required"}), 400
    orch.memory.write(key, value, writer_id="user")
    return jsonify({"ok": True})


@app.route("/api/memory/<key>", methods=["DELETE"])
def api_memory_delete(key):
    orch.memory._store.pop(key, None)
    return jsonify({"ok": True})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    orch.memory._store.clear()
    orch.bus.log.clear()
    orch.history.clear()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
