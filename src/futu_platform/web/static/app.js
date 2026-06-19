async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || res.statusText));
  return data;
}

function fmtNum(v) {
  if (v == null || v === "" || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return Math.abs(n) >= 1e4 ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : n.toFixed(2);
}

function renderTable(containerId, rows, columns, emptyText = "暫無數據") {
  const el = document.getElementById(containerId);
  if (!rows || !rows.length) {
    el.innerHTML = `<div class="empty">${emptyText}</div>`;
    return;
  }
  const head = columns.map((c) => `<th>${c.label}</th>`).join("");
  const body = rows.map((row) => {
    const tds = columns.map((c) => {
      let val = row[c.key];
      if (c.format) val = c.format(val, row);
      if (c.key === "trd_side" || c.key === "order_side" || c.key === "side") {
        const cls = String(val).toUpperCase().includes("BUY") ? "side-buy" : "side-sell";
        return `<td class="${cls}">${val ?? "—"}</td>`;
      }
      return `<td>${val ?? "—"}</td>`;
    }).join("");
    return `<tr>${tds}</tr>`;
  }).join("");
  el.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderSummary(prefix, data) {
  const el = document.getElementById(`${prefix}-summary`);
  if (data.error) {
    el.innerHTML = `<div class="error-box">${data.error}</div>`;
    return;
  }
  const info = data.acc_info || {};
  const cards = [
    { label: "帳戶數", value: (data.accounts || []).length },
    { label: "持倉數", value: data.portfolio_count ?? 0 },
    { label: "訂單數", value: data.orders_count ?? 0 },
    { label: "總資產", value: fmtNum(info.total_assets ?? info.total_asset) },
    { label: "現金", value: fmtNum(info.cash ?? info.available_cash) },
    { label: "市值", value: fmtNum(info.market_val ?? info.securities_assets) },
  ];
  el.innerHTML = cards.map((c) => `
    <div class="summary-card"><div class="label">${c.label}</div><div class="value">${c.value}</div></div>
  `).join("");
}

function renderEnvPanel(prefix, data) {
  renderSummary(prefix, data);
  renderTable(`${prefix}-portfolio`, data.portfolio, [
    { key: "code", label: "代碼" },
    { key: "stock_name", label: "名稱" },
    { key: "qty", label: "數量" },
    { key: "cost_price", label: "成本", format: fmtNum },
    { key: "market_val", label: "市值", format: fmtNum },
    { key: "pl_ratio", label: "盈虧%", format: (v) => v != null ? `${Number(v).toFixed(2)}%` : "—" },
  ]);
  renderTable(`${prefix}-orders`, data.orders, [
    { key: "order_id", label: "訂單ID" },
    { key: "code", label: "代碼" },
    { key: "order_side", label: "方向" },
    { key: "qty", label: "數量" },
    { key: "price", label: "價格", format: fmtNum },
    { key: "order_status", label: "狀態" },
  ], "今日無訂單");
}

async function refreshHealth() {
  const el = document.getElementById("health");
  try {
    const h = await api("/api/health");
    const ok = h.status === "ok";
    el.textContent = ok ? "OpenD 已連線 · 模擬+實盤" : "OpenD 未連線";
    el.className = "badge " + (ok ? "ok" : "warn");
  } catch {
    el.textContent = "API 不可用";
    el.className = "badge warn";
  }
}

async function refreshOverview() {
  const overview = await api("/api/trade/overview");
  renderEnvPanel("sim", overview.SIMULATE);
  renderEnvPanel("real", overview.REAL);
}

function fmtPnl(v) {
  if (v == null || v === "" || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const cls = n > 0 ? "pnl-pos" : n < 0 ? "pnl-neg" : "";
  return `<span class="${cls}">${n >= 0 ? "+" : ""}${fmtNum(n)}</span>`;
}

function fmtPct(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const cls = n > 0 ? "pnl-pos" : n < 0 ? "pnl-neg" : "";
  return `<span class="${cls}">${n >= 0 ? "+" : ""}${n.toFixed(2)}%</span>`;
}

function renderPaperTrading(data) {
  const status = data.status || {};
  const summary = data.summary || {};
  const cfg = status.config || {};

  document.getElementById("paper-meta").innerHTML =
    `${cfg.symbol || "—"} · ${cfg.provider || "—"} · ${cfg.strategy || "—"} · ${cfg.base_currency || "USDT"}`;

  const runBadge = document.getElementById("paper-run-badge");
  if (!status.db_exists) {
    runBadge.textContent = "尚未建立資料庫";
    runBadge.className = "badge warn";
  } else if (!status.has_data) {
    runBadge.textContent = "等待首次快照";
    runBadge.className = "badge warn";
  } else if (status.likely_running) {
    runBadge.textContent = "運行中";
    runBadge.className = "badge ok";
  } else {
    runBadge.textContent = status.last_snapshot_at ? `最後更新 ${status.last_snapshot_at}` : "已停止";
    runBadge.className = "badge";
  }

  const summaryEl = document.getElementById("paper-summary");
  if (!status.has_data) {
    summaryEl.innerHTML = `<div class="empty">尚無模擬交易資料。請在專案根目錄執行：<code>PAPER_DEMO=1 PAPER_DATA_PROVIDER=mock python main.py</code></div>`;
  } else {
    const cards = [
      { label: "淨值", value: fmtNum(summary.equity) },
      { label: "現金", value: fmtNum(summary.cash) },
      { label: "已實現 PnL", value: fmtPnl(summary.realized_pnl) },
      { label: "未實現 PnL", value: fmtPnl(summary.unrealized_pnl) },
      { label: "總損益", value: fmtPnl(summary.total_pnl) },
      { label: "報酬率", value: fmtPct(summary.return_pct) },
      { label: "持倉數", value: summary.position_count ?? 0 },
      { label: "快照時間", value: summary.timestamp ?? "—" },
    ];
    summaryEl.innerHTML = cards.map((c) => `
      <div class="summary-card"><div class="label">${c.label}</div><div class="value">${c.value}</div></div>
    `).join("");
  }

  const positions = (data.snapshot && data.snapshot.positions) || [];
  renderTable("paper-positions", positions, [
    { key: "symbol", label: "標的" },
    { key: "quantity", label: "數量", format: fmtNum },
    { key: "avg_cost", label: "均價", format: fmtNum },
    { key: "market_value", label: "市值", format: fmtNum },
  ], "目前無持倉");

  renderTable("paper-fills", data.fills || [], [
    { key: "timestamp", label: "時間" },
    { key: "symbol", label: "標的" },
    { key: "side", label: "方向" },
    { key: "quantity", label: "數量", format: fmtNum },
    { key: "fill_price", label: "成交價", format: fmtNum },
    { key: "commission", label: "手續費", format: fmtNum },
    { key: "status", label: "狀態" },
  ], "尚無成交紀錄");

  const signalsEl = document.getElementById("paper-signals");
  const signals = data.signals || [];
  if (!signals.length) {
    signalsEl.innerHTML = `<div class="empty">尚無信號紀錄</div>`;
  } else {
    const cols = [
      { key: "timestamp", label: "時間" },
      { key: "symbol", label: "標的" },
      {
        key: "signal_type",
        label: "信號",
        format: (v) => {
          const t = String(v || "").toUpperCase();
          const cls = t === "BUY" ? "signal-buy" : t === "SELL" ? "signal-sell" : "signal-hold";
          return `<span class="${cls}">${v ?? "—"}</span>`;
        },
      },
      { key: "price", label: "價格", format: fmtNum },
      { key: "reason", label: "原因" },
    ];
    const head = cols.map((c) => `<th>${c.label}</th>`).join("");
    const body = signals.map((row) => {
      const tds = cols.map((c) => {
        let val = row[c.key];
        if (c.format) val = c.format(val, row);
        return `<td>${val ?? "—"}</td>`;
      }).join("");
      return `<tr>${tds}</tr>`;
    }).join("");
    signalsEl.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }
}

async function refreshPaperTrading() {
  try {
    const data = await api("/api/paper-trading/overview");
    renderPaperTrading(data);
  } catch (e) {
    document.getElementById("paper-summary").innerHTML =
      `<div class="error-box">無法載入模擬交易資料：${e.message}</div>`;
  }
}

async function refreshAll() {
  await refreshHealth();
  await refreshOverview();
  await refreshPaperTrading();
  await loadSnapshot();
}

async function loadSnapshot() {
  const codes = document.getElementById("quote-codes").value;
  const { data } = await api(`/api/quote/snapshot?codes=${encodeURIComponent(codes)}`);
  renderTable("snapshot-table", data, [
    { key: "code", label: "代碼" },
    { key: "name", label: "名稱" },
    { key: "last_price", label: "最新價", format: fmtNum },
    { key: "open_price", label: "開盤", format: fmtNum },
    { key: "high_price", label: "最高", format: fmtNum },
    { key: "low_price", label: "最低", format: fmtNum },
    { key: "volume", label: "成交量" },
    { key: "turnover_rate", label: "換手%", format: (v) => v != null ? `${Number(v).toFixed(2)}%` : "—" },
  ]);
}

async function submitOrder(event, trdEnv) {
  event.preventDefault();
  const form = event.target;
  const fd = new FormData(form);
  const body = {
    code: fd.get("code"),
    side: fd.get("side"),
    quantity: Number(fd.get("quantity")),
    order_type: fd.get("order_type"),
    price: Number(fd.get("price")) || null,
    trd_env: trdEnv,
    confirmed: trdEnv === "REAL" ? fd.get("confirmed") === "on" : false,
  };
  const outId = trdEnv === "REAL" ? "real-order-result" : "sim-order-result";
  try {
    const result = await api("/api/trade/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    document.getElementById(outId).textContent = JSON.stringify(result, null, 2);
    await refreshOverview();
  } catch (e) {
    document.getElementById(outId).textContent = e.message;
  }
  return false;
}

async function loadStrategies() {
  const { data } = await api("/api/strategies");
  const el = document.getElementById("strategy-name");
  el.innerHTML = data.map((s) => `<option value="${s}">${s}</option>`).join("");
}

async function runStrategy() {
  const strategy = document.getElementById("strategy-name").value;
  const code = document.getElementById("strategy-code").value;
  const quantity = document.getElementById("strategy-qty").value;
  const trd_env = document.getElementById("strategy-env").value;
  const auto = document.getElementById("strategy-auto").checked;
  const confirmed = document.getElementById("strategy-confirmed").checked;
  const q = new URLSearchParams({ strategy, code, quantity, auto_trade: auto, trd_env, confirmed });
  try {
    const result = await api(`/api/strategy/run?${q}`);
    document.getElementById("strategy-out").textContent = JSON.stringify(result, null, 2);
    if (auto) await refreshOverview();
  } catch (e) {
    document.getElementById("strategy-out").textContent = e.message;
  }
}

document.getElementById("strategy-env").addEventListener("change", (e) => {
  document.getElementById("strategy-confirm-wrap").style.display =
    e.target.value === "REAL" ? "inline-flex" : "none";
});

refreshAll();
loadStrategies();
setInterval(refreshHealth, 20000);
setInterval(refreshOverview, 45000);
setInterval(refreshPaperTrading, 15000);
