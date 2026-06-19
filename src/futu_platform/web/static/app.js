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

async function refreshRiskConfig() {
  const { data } = await api("/api/risk/config");
  const enabled = data.real_trading_enabled;
  const el = document.getElementById("risk-summary");
  el.innerHTML = `
    <div class="risk-row">
      <span class="risk-dot ${enabled ? "enabled" : "disabled"}"></span>
      <strong>${enabled ? "實盤下單已開啟" : "實盤下單已關閉"}</strong>
    </div>
    <div class="risk-details">
      單筆金額上限：${fmtNum(data.real_max_order_value)} ·
      數量上限：${data.real_max_quantity} ·
      允許市場：${(data.real_allowed_prefixes || []).join(", ")} ·
      市價單：${data.real_market_order_allowed ? "允許" : "不允許"}
    </div>
  `;
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

function setupCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, rect.width || canvas.parentElement.clientWidth || 600);
  const height = Number(canvas.getAttribute("height")) || 260;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width, height };
}

function drawEmptyChart(canvasId, text) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#0a0e13";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#8fa0b8";
  ctx.font = "13px system-ui";
  ctx.fillText(text, 18, height / 2);
}

function drawGrid(ctx, width, height, pad) {
  ctx.strokeStyle = "rgba(143,160,184,0.14)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (height - pad.top - pad.bottom) * i / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
  }
  for (let i = 0; i <= 6; i++) {
    const x = pad.left + (width - pad.left - pad.right) * i / 6;
    ctx.beginPath();
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, height - pad.bottom);
    ctx.stroke();
  }
}

function makeScale(values, minPad = 0.06) {
  const nums = values.filter((v) => Number.isFinite(v));
  if (!nums.length) return { min: 0, max: 1 };
  let min = Math.min(...nums);
  let max = Math.max(...nums);
  if (min === max) {
    min -= Math.abs(min || 1) * 0.01;
    max += Math.abs(max || 1) * 0.01;
  }
  const pad = (max - min) * minPad;
  return { min: min - pad, max: max + pad };
}

function mapPoint(index, value, total, scale, width, height, pad) {
  const xSpan = width - pad.left - pad.right;
  const ySpan = height - pad.top - pad.bottom;
  const x = pad.left + (total <= 1 ? xSpan : xSpan * index / (total - 1));
  const y = height - pad.bottom - ((value - scale.min) / (scale.max - scale.min)) * ySpan;
  return { x, y };
}

function drawLine(ctx, rows, key, color, width, height, pad, scale) {
  if (!rows.length) return;
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  rows.forEach((row, idx) => {
    const value = Number(row[key]);
    const pt = mapPoint(idx, value, rows.length, scale, width, height, pad);
    if (idx === 0) ctx.moveTo(pt.x, pt.y);
    else ctx.lineTo(pt.x, pt.y);
  });
  ctx.stroke();
}

function drawAxisLabels(ctx, scale, width, height, pad) {
  ctx.fillStyle = "#8fa0b8";
  ctx.font = "11px system-ui";
  ctx.textAlign = "right";
  ctx.fillText(fmtNum(scale.max), width - 8, pad.top + 4);
  ctx.fillText(fmtNum(scale.min), width - 8, height - pad.bottom);
}

function drawPriceChart(chartData) {
  const bars = chartData.market_bars || [];
  if (!bars.length) {
    drawEmptyChart("paper-price-chart", "尚無價格資料，請先執行 python main.py");
    return;
  }
  const canvas = document.getElementById("paper-price-chart");
  const { ctx, width, height } = setupCanvas(canvas);
  const pad = { left: 12, right: 68, top: 18, bottom: 24 };
  const closes = bars.map((b) => Number(b.close));
  const scale = makeScale(closes);

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#0a0e13";
  ctx.fillRect(0, 0, width, height);
  drawGrid(ctx, width, height, pad);
  drawLine(ctx, bars, "close", "#4d9dff", width, height, pad, scale);
  drawAxisLabels(ctx, scale, width, height, pad);

  const byTime = new Map(bars.map((b, idx) => [String(b.timestamp).slice(0, 16), idx]));
  const drawMarker = (timestamp, price, side, size, hollow = false) => {
    const idx = byTime.get(String(timestamp).slice(0, 16));
    if (idx == null) return;
    const pt = mapPoint(idx, Number(price), bars.length, scale, width, height, pad);
    const isBuy = String(side).toUpperCase().includes("BUY");
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, size, 0, Math.PI * 2);
    ctx.fillStyle = isBuy ? "#2ecc87" : "#ff6b6b";
    ctx.strokeStyle = ctx.fillStyle;
    if (hollow) {
      ctx.lineWidth = 2;
      ctx.stroke();
    } else {
      ctx.globalAlpha = 0.85;
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  };

  (chartData.signals || []).forEach((s) => {
    if (s.signal_type === "BUY" || s.signal_type === "SELL") {
      drawMarker(s.timestamp, s.price, s.signal_type, 4, false);
    }
  });
  (chartData.fills || []).forEach((f) => drawMarker(f.timestamp, f.fill_price, f.side, 6, true));
}

function drawEquityChart(chartData, initialCash) {
  const rows = chartData.equity_curve || [];
  if (!rows.length) {
    drawEmptyChart("paper-equity-chart", "尚無淨值資料，請先執行 python main.py");
    return;
  }
  const canvas = document.getElementById("paper-equity-chart");
  const { ctx, width, height } = setupCanvas(canvas);
  const pad = { left: 12, right: 78, top: 18, bottom: 24 };
  const enriched = rows.map((r) => ({
    ...r,
    total_pnl: Number(r.equity) - Number(initialCash || 0),
  }));
  const scale = makeScale([
    ...enriched.map((r) => Number(r.equity)),
    ...enriched.map((r) => Number(initialCash || 0)),
  ]);

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#0a0e13";
  ctx.fillRect(0, 0, width, height);
  drawGrid(ctx, width, height, pad);
  drawLine(ctx, enriched, "equity", "#b794ff", width, height, pad, scale);

  const initialLine = Number(initialCash || 0);
  if (initialLine > 0) {
    const p0 = mapPoint(0, initialLine, enriched.length, scale, width, height, pad);
    const p1 = mapPoint(enriched.length - 1, initialLine, enriched.length, scale, width, height, pad);
    ctx.strokeStyle = "rgba(143,160,184,0.45)";
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  drawAxisLabels(ctx, scale, width, height, pad);

  const last = enriched[enriched.length - 1];
  ctx.fillStyle = Number(last.total_pnl) >= 0 ? "#2ecc87" : "#ff6b6b";
  ctx.font = "12px system-ui";
  ctx.textAlign = "left";
  ctx.fillText(`PnL ${Number(last.total_pnl) >= 0 ? "+" : ""}${fmtNum(last.total_pnl)}`, pad.left, pad.top + 4);
}

function renderPaperTrading(data) {
  const status = data.status || {};
  const summary = data.summary || {};
  const cfg = status.config || {};
  const charts = data.charts || {};

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
    drawEmptyChart("paper-price-chart", "尚無價格資料，請先執行 python main.py");
    drawEmptyChart("paper-equity-chart", "尚無淨值資料，請先執行 python main.py");
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
    drawPriceChart(charts);
    drawEquityChart(charts, summary.initial_cash);
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

function renderWorldMonitor(payload) {
  const data = payload.data || payload;
  const cfg = data.config || data;
  const runner = data.runner || {};
  const latestRun = data.latest || (data.runs || [])[0] || {};
  const recommendations = latestRun.recommendations || [];
  const primary = recommendations[0] || {};
  const running = !!(runner.running || data.running);
  const badge = document.getElementById("wm-runner-badge");
  badge.textContent = running ? "每小時監控中" : "已停止";
  badge.className = "badge " + (running ? "ok" : "warn");

  const action = primary.signal || "—";
  const cls = action === "BUY" ? "world-impact-positive" : action === "SELL" ? "world-impact-negative" : "world-impact-neutral";
  const cards = [
    { label: "狀態", value: running ? "Running" : "Stopped" },
    { label: "最新信號", value: `<span class="${cls}">${action}</span>` },
    { label: "總分", value: latestRun.score != null ? Number(latestRun.score).toFixed(2) : "—" },
    { label: "信心", value: primary.confidence != null ? `${(Number(primary.confidence) * 100).toFixed(0)}%` : "—" },
    { label: "監控標的", value: (cfg.symbols || []).join(", ") || "—" },
    { label: "自動下單", value: cfg.auto_trade ? "ON" : "OFF" },
    { label: "交易環境", value: cfg.trd_env || "SIMULATE" },
    { label: "週期", value: `${cfg.interval_seconds || 3600}s` },
  ];
  document.getElementById("wm-summary").innerHTML = cards.map((c) => `
    <div class="summary-card"><div class="label">${c.label}</div><div class="value">${c.value}</div></div>
  `).join("");

  renderTable("wm-events", data.events || [], [
    { key: "fetched_at", label: "擷取時間" },
    { key: "category", label: "類別" },
    { key: "source", label: "來源" },
    { key: "impact", label: "影響", format: (v) => v != null ? Number(v).toFixed(2) : "—" },
    { key: "title", label: "事件" },
  ], "尚無事件，請點立即掃描");

  const signalRows = (data.runs || []).flatMap((run) => (run.recommendations || []).map((rec) => ({
    timestamp: run.completed_at,
    symbol: rec.symbol,
    action: rec.signal,
    score: rec.score,
    confidence: rec.confidence,
    reason: rec.reason,
  })));
  renderTable("wm-recommendations", signalRows, [
    { key: "timestamp", label: "時間" },
    { key: "symbol", label: "標的" },
    {
      key: "action",
      label: "信號",
      format: (v) => {
        const a = String(v || "");
        const c = a === "BUY" ? "world-impact-positive" : a === "SELL" ? "world-impact-negative" : "world-impact-neutral";
        return `<span class="${c}">${a}</span>`;
      },
    },
    { key: "score", label: "分數", format: (v) => v != null ? Number(v).toFixed(2) : "—" },
    { key: "confidence", label: "信心", format: (v) => v != null ? `${(Number(v) * 100).toFixed(0)}%` : "—" },
    { key: "reason", label: "原因" },
  ], "尚無信號");

  const executionRows = (data.runs || []).flatMap((run) => (run.recommendations || []).map((rec) => ({
    timestamp: rec.generated_at || run.completed_at,
    symbol: rec.symbol,
    action: rec.signal,
    status: (rec.order || {}).status || (rec.order || {}).mode || "record_only",
    message: (rec.order || {}).message || (rec.order || {}).reason || "—",
  })));
  renderTable("wm-runs", executionRows, [
    { key: "timestamp", label: "時間" },
    { key: "symbol", label: "標的" },
    { key: "action", label: "動作" },
    { key: "status", label: "狀態" },
    { key: "message", label: "訊息" },
  ], "尚無執行紀錄");
}

async function refreshWorldMonitor() {
  try {
    const { data } = await api("/api/world-monitor/overview");
    renderWorldMonitor(data);
  } catch (e) {
    document.getElementById("wm-summary").innerHTML =
      `<div class="error-box">無法載入 World Monitor：${e.message}</div>`;
  }
}

async function runWorldMonitor() {
  const latest = document.getElementById("wm-latest-run");
  latest.textContent = "執行中…";
  try {
    const { data } = await api("/api/world-monitor/run-once", { method: "POST" });
    latest.textContent = JSON.stringify(data, null, 2);
    await refreshWorldMonitor();
  } catch (e) {
    latest.textContent = e.message;
  }
}

async function refreshAll() {
  await refreshHealth();
  await refreshOverview();
  await refreshRiskConfig();
  await refreshPaperTrading();
  await refreshWorldMonitor();
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
setInterval(refreshWorldMonitor, 60000);


function activateSection(sectionId) {
  document.querySelectorAll('.workspace-section').forEach((section) => {
    section.classList.toggle('active', section.id === sectionId);
  });
  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.section === sectionId);
  });
  if (sectionId === 'paper-trading-section') {
    setTimeout(refreshPaperTrading, 50);
  }
  if (sectionId === 'world-monitor-section') {
    setTimeout(refreshWorldMonitor, 50);
  }
}

function initNavigation() {
  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.addEventListener('click', () => activateSection(btn.dataset.section));
  });
}

window.addEventListener('resize', () => {
  const paperSection = document.getElementById('paper-trading-section');
  if (paperSection && paperSection.classList.contains('active')) {
    refreshPaperTrading();
  }
});

initNavigation();
