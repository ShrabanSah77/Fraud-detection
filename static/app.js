// AML Shield browser UI: communicates with the Python HTTP API; no training occurs here.
// Displayed laundering labels come from synthetic data.

const $ = (s) => document.querySelector(s),
  content = $("#content");
let page = 1,
  filter = "1",
  search = "",
  format = "",
  currentView = "dashboard";
const fmt = (n) => Number(n || 0).toLocaleString("en-US"),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const api = async (url, opts) => {
  let r = await fetch(url, opts),
    v = await r.json();
  if (!r.ok) throw Error(v.error || "Request failed");
  return v;
};
function notify(s) {
  let n = $("#notice");
  n.textContent = s;
  n.classList.remove("hidden");
  setTimeout(() => n.classList.add("hidden"), 4500);
}
const badge = (v) =>
  `<span class="pill ${v ? "danger" : ""}">${v ? "LABELED AML" : "NORMAL"}</span>`;
const btn = (name, fn) =>
  `<button class="ghost" onclick="${fn}">${name}</button>`;

// Switch the active page and update its heading; render the matching section asynchronously.

function navigate(v) {
  const labels = {
    dashboard: [
      "OVERVIEW",
      "Command Center",
      "Historical synthetic transaction intelligence and AML investigation activity.",
    ],
    stream: [
      "STREAM SIMULATOR",
      "Live Transaction Simulator",
      "Replay historical IBM bank transactions through actual backend model inference.",
    ],
    alerts: [
      "AML ALERTS",
      "Alert Triage",
      "Review suspicious transactions, prioritize findings, and open investigations.",
    ],
    network: [
      "NETWORK ANALYSIS",
      "Account Flow Intelligence",
      "Explore fan-in, fan-out, reciprocal transfers, and candidate cycles in indexed historical transactions.",
    ],
    cases: [
      "INVESTIGATIONS",
      "Case Management",
      "Document decisions and preserve an audit trail.",
    ],
    models: [
      "MODEL LAB",
      "Detection Model Evaluation",
      "Measured ML results from the uploaded IBM HI-Small transactions.",
    ],
  };
  const views = { dashboard, stream, alerts, network, cases, models };
  const label = labels[v];
  const render = views[v];
  if (!label || typeof render !== "function") {
    console.error("Unknown navigation page:", v);
    notify("Unable to open page: " + String(v));
    return;
  }
  currentView = v;
  document.querySelectorAll("nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === v);
  });
  const breadcrumb = $("#breadcrumb");
  const heading = $("#heading");
  const subheading = $("#subheading");
  if (!breadcrumb || !heading || !subheading || !content) {
    console.error(
      "Navigation error: missing page container or heading elements",
    );
    return;
  }
  breadcrumb.textContent = label[0];
  heading.textContent = label[1];
  subheading.textContent = label[2];
  content.innerHTML = '<div class="panel">Loading data…</div>';
  Promise.resolve()
    .then(() => render())
    .catch((e) => {
      console.error("Page render failed:", v, e);
      content.innerHTML = `<div class="panel">${esc(e.message || String(e))}</div>`;
    });
}
document
  .querySelectorAll("nav button")
  .forEach((b) => (b.onclick = () => navigate(b.dataset.view)));

// Fetch dataset statistics and draw the command-center KPI cards and activity chart.

async function dashboard() {
  let d = await api("/api/overview");
  let max = Math.max(1, ...d.daily.map((x) => x.total)),
    bars = d.daily
      .filter((_, i) => i % Math.max(1, Math.ceil(d.daily.length / 35)) === 0)
      .map(
        (x) =>
          `<div class="barwrap" title="${esc(x.day)}: ${fmt(x.total)} indexed"><div class="bar" style="height:${Math.max(2, (100 * x.total) / max)}%"></div></div>`,
      )
      .join("");
  content.innerHTML = `<div class="cards"><div class="card"><div class="label">Total dataset transactions</div><strong>${fmt(d.total)}</strong><div class="hint">Full HI-Small file counted</div></div><div class="card alert"><div class="label">Laundering-labeled transactions</div><strong>${fmt(d.positives)}</strong><div class="hint">${((100 * d.positives) / d.total).toFixed(3)}% of full dataset</div></div><div class="card"><div class="label">Indexed for investigation</div><strong>${fmt(d.indexed)}</strong><div class="hint">All labeled + sampled normal</div></div><div class="card"><div class="label">Active investigations</div><strong>${fmt(d.open_cases)}</strong><div class="hint">${fmt(d.cases)} total cases created</div></div></div><div class="twocol"><div class="panel"><h2>Transaction activity timeline</h2><div class="desc">Historical daily volumes in indexed investigation subset, not a live feed</div><div class="bar-chart">${bars}</div><div class="legend"><span><i class="dot"></i>Indexed transaction volume</span></div></div><div class="panel"><h2>Detection coverage</h2><div class="desc">Dataset composition and research scope</div><div style="font-size:38px;color:#f4b087;font-weight:800;margin:30px 0 8px">${((100 * d.positives) / d.total).toFixed(3)}%</div><p class="muted">Synthetic laundering prevalence in all ${fmt(d.total)} transactions</p><div class="pill">Best evaluated model: ${esc(d.model)}</div><p class="muted" style="font-size:12px;margin-top:20px">Labeled transactions are synthetic ground truth, not confirmed real-world crime.</p></div></div><div class="twocol"><div class="panel"><h2>Recent laundering-labeled activity</h2><div class="desc">Select any transaction to inspect account relationships and evidence</div>${txTable(d.alerts)}</div><div class="panel"><h2>Payment channels</h2><div class="desc">Indexed dataset distribution by payment format</div>${d.formats.map((x) => `<div style="display:flex;justify-content:space-between;padding:13px 0;border-bottom:1px solid #223648"><span>${esc(x.format)}</span><span class="mono">${fmt(x.flagged)} labeled / ${fmt(x.n)} indexed</span></div>`).join("")}</div></div>`;
}
function txTable(data) {
  return `<div style="overflow-x:auto"><table><thead><tr><th>Transaction</th><th>Sender → Receiver</th><th>Amount</th><th>Dataset label</th><th></th></tr></thead><tbody>${data.map((x) => `<tr><td class="mono">TX-${x.id}</td><td class="mono">${esc(x.sender)} → ${esc(x.receiver)}</td><td>${fmt(x.paid)} ${esc(x.pay_currency)}</td><td>${badge(x.label)}</td><td><button class="ghost" onclick="showTransaction(${x.id})">Investigate ↗</button></td></tr>`).join("") || '<tr><td colspan="5">No records found</td></tr>'}</tbody></table></div>`;
}

// Fetch searchable AML transactions and display alert-triage results.

async function alerts() {
  let q = new URLSearchParams({ page, label: filter, search, format }),
    d = await api("/api/transactions?" + q);
  content.innerHTML = `<div class="panel"><h2>Transaction monitoring queue</h2><p class="desc">Filtered from the indexed investigation subset. Synthetic labels are shown separately from model predictions.</p><div class="tools"><input id="search" placeholder="Search sender, receiver, bank ID" value="${esc(search)}"><select id="label"><option value="1" ${filter === "1" ? "selected" : ""}>Laundering labeled</option><option value="0" ${filter === "0" ? "selected" : ""}>Normal labeled</option><option value="" ${filter === "" ? "selected" : ""}>All indexed</option></select><button class="primary" onclick="applyFilters()">Apply filters</button></div>${txTable(d.items)}<div class="pagination"><span>Page ${d.page} · ${fmt(d.total)} matching indexed records</span><div>${btn("← Previous", "changePage(-1)")} ${btn("Next →", "changePage(1)")}</div></div></div>`;
}
function applyFilters() {
  search = $("#search").value;
  filter = $("#label").value;
  page = 1;
  alerts();
}
function changePage(n) {
  page = Math.max(1, page + n);
  alerts();
}
async function showTransaction(id) {
  let t = await api("/api/transaction/" + id);
  currentView = "detail";
  $("#breadcrumb").textContent = "TRANSACTION INTELLIGENCE";
  $("#heading").textContent = "Transaction TX-" + id;
  $("#subheading").textContent =
    "Account-level investigation and related historical activity.";
  content.innerHTML = `<div class="tools">${btn("← Back to alerts", "navigate('alerts')")}<button class="primary" onclick="openCase(${id})">${t.case ? "View investigation" : "Open investigation case"}</button></div><div class="cards"><div class="card"><div class="label">Dataset classification</div><strong style="font-size:19px">${t.label ? "Laundering" : "Normal"}</strong>${badge(t.label)}</div><div class="card"><div class="label">Payment value</div><strong style="font-size:23px">${fmt(t.paid)}</strong><div class="hint">${esc(t.pay_currency)}</div></div><div class="card"><div class="label">Channel</div><strong style="font-size:20px">${esc(t.format)}</strong></div><div class="card"><div class="label">Case status</div><strong style="font-size:20px">${esc(t.case?.status || "Not opened")}</strong></div></div><div class="split"><div class="panel"><h2>Transaction evidence</h2><div class="detail-grid">${[
    ["Timestamp", t.timestamp],
    ["Sender account", t.sender],
    ["Receiver account", t.receiver],
    ["From bank", t.from_bank],
    ["To bank", t.to_bank],
    ["Amount received", fmt(t.received) + " " + t.recv_currency],
    ["Amount paid", fmt(t.paid) + " " + t.pay_currency],
    ["Payment format", t.format],
  ]
    .map(
      ([k, v]) =>
        `<div><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`,
    )
    .join(
      "",
    )}</div></div><div class="panel"><h2>Investigation indicators</h2><div class="desc">Descriptive indicators, not independently validated laundering typologies</div><ul class="reasons">${t.reasons.map((r) => `<li>${esc(r)}</li>`).join("") || "<li>No selected indicators</li>"}</ul><p class="muted">Large-value flags use nominal amounts without exchange-rate normalization. Do not interpret them as standardized monetary thresholds.</p></div></div><div class="panel"><h2>Related account flow graph</h2><p class="desc">Edges represent actual indexed transfers involving either account. The graph is a local neighborhood, not proof of a laundering cycle.</p><div id="network"></div></div><div class="panel"><h2>Related transactions</h2>${txTable(t.related)}</div>`;
  drawNetwork(t.network, t.sender, t.receiver);
  const tools = content.querySelector(".tools");
  if (tools) {
    const b = document.createElement("button");
    b.className = "ghost";
    b.textContent = "Analyze sender network";
    b.onclick = () => {
      window.lastNetworkAccount = t.sender;
      navigate("network");
    };
    tools.appendChild(b);
  }
}

// Render observed account connections as an SVG graph.

function drawNetwork(edges, a, b) {
  let ids = [
      ...new Set([a, b, ...edges.flatMap((e) => [e.sender, e.receiver])]),
    ].slice(0, 26),
    N = ids.length,
    w = 900,
    h = 310,
    cx = w / 2,
    cy = h / 2,
    pos = {};
  ids.forEach((id, i) => {
    let theta = (2 * Math.PI * i) / N;
    pos[id] = [
      cx + Math.cos(theta) * Math.min(320, 100 + N * 8),
      cy + Math.sin(theta) * 125,
    ];
  });
  let lines = edges
    .filter((e) => pos[e.sender] && pos[e.receiver])
    .map(
      (e) =>
        `<line x1="${pos[e.sender][0]}" y1="${pos[e.sender][1]}" x2="${pos[e.receiver][0]}" y2="${pos[e.receiver][1]}"/>`,
    )
    .join("");
  let nodes = ids
    .map(
      (id) =>
        `<circle class="${id === a || id === b ? "focus" : ""}" cx="${pos[id][0]}" cy="${pos[id][1]}" r="${id === a || id === b ? 11 : 7}"><title>${esc(id)}</title></circle><text x="${pos[id][0] + 9}" y="${pos[id][1] - 9}">${esc(id)}</text>`,
    )
    .join("");
  $("#network").innerHTML =
    `<svg class="network" viewBox="0 0 ${w} ${h}" role="img" aria-label="Transaction account relationship graph">${lines}${nodes}</svg>`;
}

// Create or reopen a transaction investigation case.

async function openCase(id) {
  let r = await api("/api/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transaction_id: id }),
  });
  notify("Investigation case opened");
  showCase(r.id);
}

// List investigation cases stored in SQLite.

async function cases() {
  let d = await api("/api/cases");
  content.innerHTML = `<div class="panel"><h2>Investigation case registry</h2><p class="desc">Persistent local SQLite records with analyst notes and audit history. Select a case to review.</p><div style="overflow-x:auto"><table><thead><tr><th>Case</th><th>Transaction</th><th>Status</th><th>Priority</th><th>Assigned</th><th>Last updated</th><th></th></tr></thead><tbody>${d.map((c) => `<tr><td class="mono">CASE-${c.id}</td><td>TX-${c.transaction_id}</td><td><span class="pill ${c.status === "Escalated" ? "danger" : ""}">${esc(c.status)}</span></td><td>${esc(c.priority)}</td><td>${esc(c.assignee)}</td><td>${esc(c.updated_at)}</td><td>${btn("Review ↗", `showCase(${c.id})`)}</td></tr>`).join("") || '<tr><td colspan="7">No cases yet. Open an AML alert and create the first investigation.</td></tr>'}</tbody></table></div></div>`;
}

// Display the selected case and its audit history.

async function showCase(id) {
  let d = await api("/api/case/" + id),
    c = d.case;
  $("#breadcrumb").textContent = "CASE MANAGEMENT";
  $("#heading").textContent = "Investigation CASE-" + id;
  $("#subheading").textContent =
    "Review the evidence, assign responsibility, and document your decision.";
  content.innerHTML = `<div class="tools">${btn("← All investigations", "navigate('cases')")} ${btn("View transaction", `showTransaction(${c.transaction_id})`)}</div><div class="split"><div class="panel"><h2>Case workflow</h2><p class="desc">Transaction TX-${c.transaction_id} · Created ${esc(c.created_at)}</p><div class="detail-grid"><div><small>Status</small><select id="caseStatus">${["Open", "Investigating", "Escalated", "Closed", "Dismissed"].map((x) => `<option ${x === c.status ? "selected" : ""}>${x}</option>`).join("")}</select></div><div><small>Priority</small><select id="casePriority">${["Low", "Medium", "High", "Critical"].map((x) => `<option ${x === c.priority ? "selected" : ""}>${x}</option>`).join("")}</select></div></div><p class="muted">Assigned analyst</p><input id="assignee" value="${esc(c.assignee)}"><p class="muted">Investigator notes and findings</p><textarea id="notes">${esc(c.notes)}</textarea><p><button class="primary" onclick="saveCase(${id})">Save case and audit event</button></p></div><div class="panel"><h2>Audit trail</h2><p class="desc">Local chronological history of case activity</p>${d.audit.map((a) => `<div style="padding:14px 0;border-bottom:1px solid #294055"><div><strong>${esc(a.action)}</strong> <span class="muted" style="float:right">${esc(a.created_at)}</span></div><p class="muted">${esc(a.details)}</p></div>`).join("")}</div></div>`;
}

// Send investigator edits to the backend and refresh the case view.

async function saveCase(id) {
  let body = {
    status: $("#caseStatus").value,
    priority: $("#casePriority").value,
    assignee: $("#assignee").value,
    notes: $("#notes").value,
  };
  await api("/api/case/" + id, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  notify("Case updated and audit event saved");
  showCase(id);
}

// Show stored evaluation metrics for the trained classifiers.

async function models() {
  let d = await api("/api/overview");
  content.innerHTML = `<div class="panel"><h2>Model comparison · measured results</h2><p class="desc">Stratified held-out split from a case-enriched sampled pool; the original 5.08M transactions are not the evaluation denominator.</p><div style="overflow-x:auto"><div class="modelrow head"><span>MODEL</span><span>PRECISION</span><span>RECALL</span><span>F1</span><span>AUPRC</span><span>ACCURACY</span></div>${Object.entries(
    d.metrics,
  )
    .map(
      ([name, m]) =>
        `<div class="modelrow"><strong>${esc(name)}</strong>${["precision", "recall", "f1", "auprc", "accuracy"].map((k) => `<span>${(100 * m[k]).toFixed(2)}%</span>`).join("")}</div>`,
    )
    .join(
      "",
    )}</div><p class="muted">Best model selected by sampled-test AUPRC: <strong>${esc(d.model)}</strong>. This is a research comparison, not calibrated production probability.</p></div><div class="panel"><h2>Confusion matrices</h2><div class="split">${Object.entries(
    d.metrics,
  )
    .map(
      ([name, m]) =>
        `<div><h3>${esc(name)}</h3><div class="detail-grid">${[
          ["True negatives", m.confusion_matrix[0][0]],
          ["False positives", m.confusion_matrix[0][1]],
          ["False negatives", m.confusion_matrix[1][0]],
          ["True positives", m.confusion_matrix[1][1]],
        ]
          .map(
            ([a, b]) =>
              `<div><small>${a}</small><strong>${fmt(b)}</strong></div>`,
          )
          .join("")}</div></div>`,
    )
    .join(
      "",
    )}</div></div><div class="panel"><h2>Methodology and limitations</h2><p>${esc(d.evaluation_note)}</p><p class="muted">Training uses transaction-level amount, payment format, currencies, interbank, self-transfer, and hour features. No label, future event, or pattern-file membership is used as a feature. Train/test records are split randomly; repeated accounts may cross splits. For publication-quality results, evaluate using temporal/account-disjoint splits and preserve the original base rate.</p><p class="muted">This version intentionally does not claim to train XGBoost or implement SMOTE. Its two fitted models are Logistic Regression and Random Forest.</p></div>`;
}

// Account flow intelligence: real records from /api/network, no simulated graph edges.
// Show the account search and observed transaction-network visualization.

async function network(account = "") {
  const selected = account || window.lastNetworkAccount || "";
  content.innerHTML = `<div class="panel"><h2>Account network analysis</h2><p class="desc">Find observed relationships and exploratory transaction patterns within the indexed IBM HI-Small subset.</p><div class="tools"><input id="networkAccount" placeholder="Enter sender or receiver account" value="${esc(selected)}"><button class="primary" id="networkSearch">Analyze account</button></div><p class="muted">Tip: open a transaction and click Analyze sender network to prefill an account.</p></div><div id="networkResults"></div>`;
  $("#networkSearch").onclick = () => loadNetwork($("#networkAccount").value);
  if (selected) await loadNetwork(selected);
}

// Request account relationships from the backend and draw the graph.

async function loadNetwork(account) {
  account = String(account || "").trim();
  if (!account) {
    notify("Enter an account ID");
    return;
  }
  window.lastNetworkAccount = account;
  let d;
  try {
    d = await api("/api/network?" + new URLSearchParams({ account }));
  } catch (e) {
    notify(e.message);
    return;
  }
  const out = $("#networkResults");
  if (!out) return;
  const stats = [
    ["Incoming transactions", d.incoming],
    ["Outgoing transactions", d.outgoing],
    ["Unique senders", d.sources],
    ["Unique recipients", d.targets],
  ];
  out.innerHTML = `<div class="cards">${stats.map(([name, n]) => `<div class="card"><div class="label">${name}</div><strong>${fmt(n)}</strong></div>`).join("")}</div><div class="panel"><h2>Observed indicators</h2><p class="desc">${esc(d.scope)}</p>${d.indicators.length ? d.indicators.map((x) => `<p><strong>${esc(x.type)}</strong> — ${esc(x.detail)}</p>`).join("") : '<p class="muted">No selected pattern thresholds reached in the retrieved subset.</p>'}${d.cycles.length ? `<p class="muted">Candidate paths: ${d.cycles.map((x) => esc(x.join(" → "))).join("; ")}</p>` : ""}</div><div class="panel"><h2>Observed account connections</h2><div id="network"></div></div><div class="panel"><h2>Supporting transactions</h2>${txTable(d.edges.slice(0, 100))}</div>`;
  if (d.edges.length) drawNetwork(d.edges, account, account);
  else
    $("#network").textContent =
      "No indexed transactions found for this account.";
}

navigate("dashboard");

// Streaming is driven by real HTTP requests; each step runs inference and persists events in SQLite.

let streamTimer = null,
  streamBusy = false;
async function streamControl(action, batch = 5) {
  let d = await api("/api/stream/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, batch }),
  });
  if (currentView === "stream") renderStream(d);
  return d;
}
function streamStopTimer() {
  if (streamTimer) {
    clearInterval(streamTimer);
    streamTimer = null;
  }
}

// Display historical transaction replay controls and recent scoring events.

async function stream() {
  streamStopTimer();
  let d = await api("/api/stream");
  renderStream(d);
  if (d.state.running) streamStartTimer();
}
function streamStartTimer() {
  streamStopTimer();
  streamTimer = setInterval(async () => {
    if (currentView !== "stream") {
      streamStopTimer();
      return;
    }
    if (streamBusy) return;
    streamBusy = true;
    try {
      let d = await streamControl("step", 5);
      if (!d.state.running) streamStopTimer();
    } catch (e) {
      notify(e.message);
      streamStopTimer();
    } finally {
      streamBusy = false;
    }
  }, 1500);
}
async function streamStart() {
  let d = await streamControl("start");
  if (d.state.running) streamStartTimer();
}
async function streamPause() {
  streamStopTimer();
  await streamControl("pause");
}
async function streamReset() {
  streamStopTimer();
  await streamControl("reset");
}
async function streamNext() {
  streamStopTimer();
  await streamControl("start");
  await streamControl("step", 1);
  await streamControl("pause");
}
function renderStream(d) {
  if (currentView !== "stream") return;
  let st = d.state;
  content.innerHTML = `<div class="panel"><h2>Simulated bank transaction ingestion</h2><p class="desc">${esc(d.mode)}. Every step sends a request to the Python backend, scores new historical records using the saved trained model, and saves alert events to SQLite. No dataset label is used for scoring.</p><div class="tools"><button class="primary" onclick="streamStart()">▶ Start replay</button><button class="ghost" onclick="streamPause()">Ⅱ Pause</button><button class="ghost" onclick="streamNext()">→ One transaction</button><button class="ghost" onclick="streamReset()">↺ Reset replay</button></div></div><div class="cards"><div class="card"><div class="label">Replay state</div><strong style="font-size:22px">${st.running ? "STREAMING" : "PAUSED"}</strong></div><div class="card"><div class="label">Processed by backend</div><strong>${fmt(st.processed)}</strong></div><div class="card alert"><div class="label">Generated risk alerts</div><strong>${fmt(st.alerts)}</strong></div><div class="card"><div class="label">Alert rate</div><strong>${st.processed ? ((100 * st.alerts) / st.processed).toFixed(1) : "0.0"}%</strong></div></div><div class="panel"><h2>Incoming bank transactions & detection decisions</h2><p class="desc">Risk score = uncalibrated ML output plus illustrative rules. Synthetic ground truth is displayed only for comparison after inference. Select a row to investigate.</p><div style="overflow-x:auto"><table><thead><tr><th>Event</th><th>Historical timestamp</th><th>Account flow</th><th>Amount</th><th>ML score</th><th>Risk</th><th>Alert</th><th>Dataset label</th><th></th></tr></thead><tbody>${d.events.map((e) => `<tr><td class="mono">#${e.id}</td><td>${esc(e.timestamp)}</td><td class="mono">${esc(e.sender)} → ${esc(e.receiver)}</td><td>${fmt(e.paid)} ${esc(e.pay_currency)}</td><td>${(e.model_score * 100).toFixed(1)}%</td><td><span class="pill ${e.risk_score >= 60 ? "danger" : ""}">${e.risk_score} / ${esc(e.severity)}</span></td><td>${e.alert ? "⚑ Flagged" : "—"}</td><td>${badge(e.synthetic_label)}</td><td><button class="ghost" onclick="showTransaction(${e.transaction_id})">Investigate ↗</button></td></tr>`).join("") || '<tr><td colspan="9">No transactions replayed yet. Press Start replay or One transaction.</td></tr>'}</tbody></table></div></div><div class="panel"><h2>How the simulation works</h2><p class="muted">Browser → POST /api/stream/control → Python model.predict_proba → rules → SQLite stream_events → dashboard refresh. The source is the actual indexed subset of HI-Small, ordered by historical timestamps. It is not the full 5.08M-row stream and not a real bank connection. Alerts indicate review priority, not proven laundering.</p></div>`;
}
