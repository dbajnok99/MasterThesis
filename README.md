# Securing Agentic Architectures

Diploma thesis project — [E191 Institute of Computer Engineering](https://www.tuwien.at/en/inf/e191), TU Wien
**Advisor:** Univ.Prof. Ezio Bartocci
**Field:** Computer Sciences

---

## Overview

This repository contains the experimental prototype for the thesis *Securing Agentic Architectures*, which investigates the security properties of LLM-based multi-agent systems (MAS).

The prototype is an intentionally vulnerable multi-agent system used to:

1. Characterise the attack surface of agentic architectures
2. Simulate concrete attacks against the system
3. Evaluate defences and measure their trade-offs with performance

---

## Research Questions

| # | Topic | Question |
|---|---|---|
| 1 | **Attack Surface** | What are the distinct attack surfaces in LLM-based multi-agent systems? |
| 2 | **Prompt Injection** | How does prompt injection propagate across agents via shared memory or message passing? |
| 3 | **Data Exfiltration** | Under what conditions can one agent extract sensitive data from another? |
| 4 | **Memory Manipulation** | How can shared context stores be poisoned? |
| 5 | **Authorization & Trust** | Can trust or reputation models reduce malicious agent impact? |
| 6 | **Defense Evaluation** | What are the trade-offs between security and performance? |

---

## Architecture

```
User
 │  HTTP
 ▼
Flask (app.py)
 │
 ▼
Orchestrator
 ├── SharedMemory       ← versioned key/value store (attack surface: memory poisoning)
 ├── MessageBus         ← pub/sub routing + audit log (attack surface: message injection)
 ├── PlannerAgent       ← decomposes tasks, synthesizes results (OpenAI)
 └── ToolAgent          ← executes subtasks via LangGraph + tools
      ├── file_read / file_write   (sandboxed workspace)
      ├── calculate
      ├── get_weather              (Open-Meteo API)
      └── get_stock_price          (Yahoo Finance)
```

The two agents communicate exclusively through the `MessageBus` and `SharedMemory`, mirroring the architecture of real-world agentic frameworks.

---

## Running the Prototype

### 1. Set your API key

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the server

```bash
python3 app.py
```

### 4. Open the UI

Navigate to [http://localhost:5000](http://localhost:5000)

---

## Web UI

The interface has two panels:

- **Chat** — send tasks to the multi-agent system and see responses. Conversation history is maintained across turns.
- **Debug panel** — inspect the internal state of each run:
  - *Message Flow* — messages exchanged on the internal bus
  - *Memory* — shared memory state, editable directly
  - *Tool Calls* — every tool invocation with arguments and raw output

---

## Sandbox

The `sandbox/` directory is the agent's file workspace. It contains fictional sensitive files used as exfiltration targets in attack experiments:

| File | Contents |
|---|---|
| `credentials.txt` | Fake API keys and passwords |
| `config.json` | Fake database/SMTP configuration |
| `users.csv` | Fake user records with roles |

See [`sandbox/README.md`](sandbox/README.md) for details on the attack scenarios each file supports.

---

## References

- Greshake et al. — [From prompt injections to protocol exploits: Threats in LLM-powered AI agents workflows](https://www.sciencedirect.com/science/article/pii/S2405959525001997)
- [AI Agents Under Threat: A Survey of Key Security Challenges and Future Pathways](https://dl.acm.org/doi/10.1145/3716628)
- [The Emerged Security and Privacy of LLM Agent: A Survey with Case Studies](https://dl.acm.org/doi/full/10.1145/3773080)
