/* ── State ──────────────────────────────────────────────────── */
const runs = [];         // [{messages, memory, tool_calls}] one per agent reply
let   activeRun = null;  // index into runs currently shown in debug panel
let   isRunning = false;

/* ── DOM refs ───────────────────────────────────────────────── */
const messagesEl  = document.getElementById("messages");
const inputEl     = document.getElementById("task-input");
const sendBtn     = document.getElementById("send-btn");
const memoryBar   = document.getElementById("memory-bar");
const flowPane    = document.getElementById("pane-flow");
const memPane     = document.getElementById("pane-memory");
const toolsPane   = document.getElementById("pane-tools");

/* ── Tab switching ──────────────────────────────────────────── */
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("pane-" + btn.dataset.tab).classList.add("active");
  });
});

/* ── Submit task ────────────────────────────────────────────── */
async function submitTask() {
  const task = inputEl.value.trim();
  if (!task || isRunning) return;

  isRunning = true;
  sendBtn.disabled = true;
  inputEl.disabled = true;

  appendUserMessage(task);
  inputEl.value = "";

  const thinkingEl = appendThinking();

  try {
    const res  = await fetch("/api/run", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ task }),
    });
    const data = await res.json();

    thinkingEl.remove();

    const runIdx = runs.length;
    runs.push({ messages: data.messages, memory: data.memory, tool_calls: data.tool_calls });

    appendAgentMessage(data.result, runIdx);
    refreshMemoryBar(data.memory);
    showDebugRun(runIdx);

  } catch (err) {
    thinkingEl.remove();
    appendAgentMessage("Error: " + err.message, null);
  } finally {
    isRunning = false;
    sendBtn.disabled = false;
    inputEl.disabled = false;
    inputEl.focus();
  }
}

sendBtn.addEventListener("click", submitTask);
inputEl.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitTask(); }
});

/* ── Message rendering ──────────────────────────────────────── */
function appendUserMessage(text) {
  const el = document.createElement("div");
  el.className = "message user";
  el.innerHTML = `
    <div class="bubble">${esc(text)}</div>
    <div class="message-meta">${timestamp()}</div>
  `;
  messagesEl.appendChild(el);
  scrollBottom();
}

function appendAgentMessage(text, runIdx) {
  const el = document.createElement("div");
  el.className = "message agent";
  const debugLink = runIdx !== null
    ? `<button class="debug-link" onclick="showDebugRun(${runIdx})">view debug ↗</button>`
    : "";
  el.innerHTML = `
    <div class="bubble">${esc(text)}</div>
    <div class="message-meta">${timestamp()} ${debugLink}</div>
  `;
  messagesEl.appendChild(el);
  scrollBottom();
}

function appendThinking() {
  const el = document.createElement("div");
  el.className = "message agent";
  el.innerHTML = `
    <div class="thinking">
      <div class="dot-anim"><span></span><span></span><span></span></div>
      Agents working…
    </div>
  `;
  messagesEl.appendChild(el);
  scrollBottom();
  return el;
}

/* ── Debug panel ────────────────────────────────────────────── */
function showDebugRun(idx) {
  activeRun = idx;
  const run = runs[idx];
  renderFlow(run.messages);
  renderMemory(run.memory);
  renderToolCalls(run.tool_calls);
}

function renderFlow(messages) {
  if (!messages || messages.length === 0) {
    flowPane.innerHTML = `<p class="flow-empty">No messages for this run.</p>`;
    return;
  }
  flowPane.innerHTML = messages.map(m => `
    <div class="flow-msg">
      <div class="flow-header">
        <span class="flow-sender">${esc(m.sender)}</span>
        <span class="flow-arrow">→</span>
        <span class="flow-receiver">${esc(m.receiver)}</span>
        <span class="flow-type ${m.type}">${m.type}</span>
      </div>
      <div class="flow-body">${esc(m.content)}</div>
    </div>
  `).join("");
}

function renderMemory(memory) {
  const keys = Object.keys(memory || {});
  const entries = keys.length === 0
    ? `<p style="color:var(--muted);font-size:12px;font-style:italic">Memory is empty.</p>`
    : keys.map(k => {
        const e = memory[k];
        return `
          <div class="mem-entry">
            <span class="mem-key">${esc(k)}</span>
            <span class="mem-value">${esc(e.value)}</span>
            <span class="mem-meta">v${e.version} · ${esc(e.owner)}</span>
          </div>`;
      }).join("");

  memPane.innerHTML = `
    <div class="memory-section">
      <h3>Current State</h3>
      ${entries}
    </div>
    <div class="memory-section">
      <h3>Add / Update</h3>
      <div class="add-memory-form">
        <input id="mem-key-input" placeholder="key" />
        <input id="mem-val-input" placeholder="value" />
        <button class="btn btn-primary btn-sm" onclick="addMemoryEntry()">Set</button>
      </div>
    </div>
  `;
}

function renderToolCalls(toolCalls) {
  if (!toolCalls || toolCalls.length === 0) {
    toolsPane.innerHTML = `<p class="tool-empty">No tools called in this run.</p>`;
    return;
  }
  toolsPane.innerHTML = toolCalls.map(tc => `
    <div class="tool-call">
      <div class="tool-header">
        <span class="tool-name">${esc(tc.tool)}</span>
        <span class="tool-args">${esc(JSON.stringify(tc.args))}</span>
      </div>
      <div class="tool-output">${esc(tc.output)}</div>
    </div>
  `).join("");
}

/* ── Memory bar (top of input area) ────────────────────────── */
function refreshMemoryBar(memory) {
  const keys = Object.keys(memory || {});
  if (keys.length === 0) {
    memoryBar.innerHTML = `<span class="memory-bar-label">Memory</span><span class="pill-empty">empty</span>`;
    return;
  }
  const pills = keys.map(k => `
    <div class="pill">
      <span class="pill-key">${esc(k)}</span>
      <span>: ${esc(memory[k].value.slice(0, 30))}${memory[k].value.length > 30 ? "…" : ""}</span>
      <button class="pill-del" onclick="deleteMemory('${esc(k)}')">×</button>
    </div>
  `).join("");
  memoryBar.innerHTML = `<span class="memory-bar-label">Memory</span>${pills}`;
}

/* ── Memory actions ─────────────────────────────────────────── */
async function addMemoryEntry() {
  const key   = document.getElementById("mem-key-input").value.trim();
  const value = document.getElementById("mem-val-input").value.trim();
  if (!key) return;
  await fetch("/api/memory", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ key, value }),
  });
  const data = await (await fetch("/api/memory")).json();
  refreshMemoryBar(data);
  renderMemory(data);
}

async function deleteMemory(key) {
  await fetch(`/api/memory/${encodeURIComponent(key)}`, { method: "DELETE" });
  const data = await (await fetch("/api/memory")).json();
  refreshMemoryBar(data);
  // update the debug panel memory view too
  if (activeRun !== null) renderMemory(data);
}

/* ── Reset ──────────────────────────────────────────────────── */
async function resetAll() {
  if (!confirm("Clear all memory and message history?")) return;
  await fetch("/api/reset", { method: "POST" });
  messagesEl.innerHTML = "";
  runs.length = 0;
  activeRun = null;
  refreshMemoryBar({});
  renderFlow([]);
  renderMemory({});
  renderToolCalls([]);
}

/* ── Helpers ────────────────────────────────────────────────── */
function esc(str) {
  return String(str)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function timestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/* ── Init ───────────────────────────────────────────────────── */
(async () => {
  const data = await (await fetch("/api/memory")).json();
  refreshMemoryBar(data);
  renderFlow([]);
  renderMemory(data);
  renderToolCalls([]);
  inputEl.focus();
})();
