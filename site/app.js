/* Competitor Watch dashboard — vanilla JS + Chart.js, no build step. */
(() => {
  "use strict";

  const PALETTE = ["#04CC9E", "#4D8DFF", "#FFB547", "#FF6B6B", "#B98CFF", "#5CE1E6", "#F78FB3"];
  const TYPES = {
    price_down: { label: "Price drop", icon: "↓", color: "#04CC9E" },
    price_up: { label: "Price rise", icon: "↑", color: "#FF6B6B" },
    new: { label: "New", icon: "+", color: "#4D8DFF" },
    removed: { label: "Removed", icon: "−", color: "#8FB0B8" },
    changed: { label: "Updated", icon: "•", color: "#FFB547" },
  };
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (v, cur) => v == null ? "—" : new Intl.NumberFormat("en", { style: "currency", currency: cur || "USD", maximumFractionDigits: 2 }).format(v);
  const pct = (v) => v == null ? "" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
  const fmtDate = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const fmtDateTime = (iso) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short" });

  const state = { data: null, type: "", target: "", q: "", sort: "changes", charts: {} };

  async function init() {
    const res = await fetch("data/dashboard.json", { cache: "no-cache" });
    state.data = await res.json();
    const d = state.data;
    d.targetById = Object.fromEntries(d.targets.map((t) => [t.id, t]));
    d.productById = Object.fromEntries(d.products.map((p) => [p.id, p]));

    $("#updated").textContent = `Updated ${fmtDateTime(d.generated_at)}`;
    if (d.sample_until) {
      $("#notice").hidden = false;
      $("#notice-text").textContent = `Prices and products are scraped live from public scraping-practice sites. Those sites never change, so history up to ${fmtDate(d.sample_until)} is simulated sample data (shaded in charts, tagged "sample" in the feed) to demonstrate change detection. Everything after is real.`;
    }

    renderKpis();
    renderSources();
    buildFilters();
    renderFeed();
    renderTable();
    if (window.Chart) charts(); else window.addEventListener("load", charts);
  }

  // ---------- KPIs ----------
  function renderKpis() {
    const d = state.data;
    const last = d.daily.length ? d.daily[d.daily.length - 1].date : null;
    const since = (days) => {
      const cut = new Date(Date.parse(d.generated_at) - days * 864e5).toISOString();
      return d.changes.filter((c) => c.detected_at >= cut);
    };
    const c30 = since(30);
    const moves = c30.filter((c) => c.pct_change != null && (c.type === "price_up" || c.type === "price_down"));
    const avgMove = moves.length ? moves.reduce((a, c) => a + c.pct_change, 0) / moves.length : 0;
    const drops = moves.filter((c) => c.type === "price_down").length;
    const kpis = [
      { label: "Products tracked", value: d.products.length, sub: `${d.targets.length} sources · ${new Set(d.targets.map((t) => t.site)).size} sites` },
      { label: "Changes · 7 days", value: since(7).length, sub: last ? `last event ${fmtDate(last)}` : "no events yet" },
      { label: "Price moves · 30d", value: moves.length, sub: `${drops} drops · ${moves.length - drops} rises` },
      { label: "Avg move · 30d", value: pct(avgMove), cls: avgMove > 0 ? "up" : "down", sub: "mean % per price event" },
      { label: "New / removed · 30d", value: `${c30.filter((c) => c.type === "new").length} / ${c30.filter((c) => c.type === "removed").length}`, sub: "assortment changes" },
    ];
    $("#kpis").innerHTML = kpis.map((k) => `
      <div class="kpi"><div class="kpi__label">${k.label}</div>
      <div class="kpi__value ${k.cls || ""}">${esc(k.value)}</div><div class="kpi__sub">${esc(k.sub)}</div></div>`).join("");
  }

  // ---------- sources ----------
  function renderSources() {
    $("#sources").innerHTML = state.data.targets.map((t) => {
      const r = t.last_run || {};
      const ok = r.status === "ok";
      return `<div class="source"><h3>${esc(t.name)}</h3>
        <p><a href="${esc(t.url)}" rel="noopener">${esc(t.site)}</a> · ${t.count} items · ${esc(t.currency)}</p>
        <p class="${ok ? "ok" : "err"}">${ok ? "● healthy" : "● " + esc(r.status || "never run")} ${r.run_at ? "· " + fmtDateTime(r.run_at) : ""}</p></div>`;
    }).join("");
  }

  // ---------- filters ----------
  function buildFilters() {
    const chips = [["", "All"], ...Object.entries(TYPES).map(([k, v]) => [k, v.label])];
    $("#type-chips").innerHTML = chips.map(([k, l]) => `<button class="chip" data-type="${k}" aria-pressed="${k === state.type}">${l}</button>`).join("");
    $("#type-chips").addEventListener("click", (e) => {
      const b = e.target.closest(".chip"); if (!b) return;
      state.type = b.dataset.type;
      document.querySelectorAll("#type-chips .chip").forEach((c) => c.setAttribute("aria-pressed", c === b));
      renderFeed();
    });
    const sel = $("#target-filter");
    state.data.targets.forEach((t) => sel.insertAdjacentHTML("beforeend", `<option value="${esc(t.id)}">${esc(t.name)}</option>`));
    sel.addEventListener("change", () => { state.target = sel.value; renderFeed(); renderTable(); });
    $("#search").addEventListener("input", (e) => { state.q = e.target.value.toLowerCase(); renderTable(); });
    $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; renderTable(); });
  }

  // ---------- feed ----------
  function renderFeed() {
    const d = state.data;
    const items = d.changes.filter((c) => (!state.type || c.type === state.type) && (!state.target || c.target === state.target));
    $("#feed-count").textContent = `${items.length} events${state.target ? " · " + d.targetById[state.target].name : ""}`;
    $("#feed").innerHTML = items.slice(0, 150).map((c) => {
      const t = TYPES[c.type];
      let delta = "";
      if (c.type === "price_up" || c.type === "price_down") delta = `<span class="${c.type === "price_up" ? "up" : "down"}">${pct(c.pct_change)}</span><div class="meta">${money(c.new_price, c.currency)}</div>`;
      else if (c.type === "changed") delta = `<span class="meta">${esc(Object.keys(c.fields).join(", "))}</span>`;
      else delta = `<span class="meta">${money(c.new_price ?? c.old_price, c.currency)}</span>`;
      return `<li data-id="${esc(c.product_id)}" title="${esc(c.name)}">
        <span class="ico ico--${c.type}" aria-label="${t.label}">${t.icon}</span>
        <div style="min-width:0"><div class="name">${esc(c.name)}</div>
        <div class="meta">${esc(d.targetById[c.target]?.name || c.target)} · ${fmtDate(c.detected_at)}${c.sample ? '<span class="tag">sample</span>' : ""}</div></div>
        <div class="delta">${delta}</div></li>`;
    }).join("") || `<li class="meta">No events match this filter.</li>`;
  }
  $("#feed").addEventListener("click", (e) => { const li = e.target.closest("li[data-id]"); if (li) openDetail(li.dataset.id); });

  // ---------- table ----------
  function spark(history, w = 96, h = 26) {
    if (!history || history.length < 2) return `<svg class="spark" width="${w}" height="${h}"><line x1="0" y1="${h / 2}" x2="${w}" y2="${h / 2}" stroke="#8FB0B8" stroke-opacity=".4" stroke-dasharray="3 3"/></svg>`;
    const t0 = Date.parse(history[0][0]), t1 = Date.parse(history[history.length - 1][0]) || t0 + 1;
    const ys = history.map((p) => p[1]); const lo = Math.min(...ys), hi = Math.max(...ys) || 1;
    const x = (d) => ((Date.parse(d) - t0) / (t1 - t0 || 1)) * (w - 4) + 2;
    const y = (v) => h - 3 - ((v - lo) / (hi - lo || 1)) * (h - 6);
    let path = `M${x(history[0][0])},${y(history[0][1])}`;
    for (let i = 1; i < history.length; i++) path += ` H${x(history[i][0])} V${y(history[i][1])}`;
    const lastUp = ys[ys.length - 1] >= ys[0];
    return `<svg class="spark" width="${w}" height="${h}" aria-hidden="true"><path d="${path}" fill="none" stroke="${lastUp ? "#FF6B6B" : "#04CC9E"}" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
  }
  function renderTable() {
    const d = state.data;
    let rows = d.products.filter((p) => (!state.target || p.target === state.target) && (!state.q || p.name.toLowerCase().includes(state.q)));
    const sorters = {
      changes: (a, b) => b.changes - a.changes,
      pct: (a, b) => Math.abs(b.pct_since_first) - Math.abs(a.pct_since_first),
      "price-desc": (a, b) => (b.price ?? 0) - (a.price ?? 0),
      "price-asc": (a, b) => (a.price ?? 0) - (b.price ?? 0),
      name: (a, b) => a.name.localeCompare(b.name),
    };
    rows = rows.sort(sorters[state.sort]);
    $("#table-count").textContent = `${rows.length} of ${d.products.length} products`;
    $("#rows").innerHTML = rows.map((p) => `<tr data-id="${esc(p.id)}">
      <td><div class="prod"><img src="${esc(p.image)}" alt="" loading="lazy" width="34" height="34"><span>${esc(p.name)}</span></div></td>
      <td><span class="pill">${esc(d.targetById[p.target]?.category || p.target)}</span></td>
      <td class="num">${money(p.price, p.currency)}</td>
      <td class="num ${p.pct_since_first > 0 ? "up" : p.pct_since_first < 0 ? "down" : ""}">${p.pct_since_first ? pct(p.pct_since_first) : "—"}</td>
      <td>${spark(p.history)}</td>
      <td class="num">${p.changes}</td></tr>`).join("");
  }
  $("#rows").addEventListener("click", (e) => { const tr = e.target.closest("tr[data-id]"); if (tr) openDetail(tr.dataset.id); });

  // ---------- charts ----------
  const sampleShade = {
    id: "sampleShade",
    beforeDatasetsDraw(chart, _a, opts) {
      if (!opts.until) return;
      const labels = chart.data.labels; const idx = labels.findLastIndex((l) => l <= opts.until);
      if (idx < 0) return;
      const { ctx, chartArea: a, scales: { x } } = chart;
      const right = Math.min(a.right, x.getPixelForValue(idx) + (labels.length > 1 ? (x.getPixelForValue(1) - x.getPixelForValue(0)) / 2 : 0));
      ctx.save(); ctx.fillStyle = "rgba(255,181,71,.06)"; ctx.fillRect(a.left, a.top, right - a.left, a.bottom - a.top);
      ctx.fillStyle = "rgba(255,181,71,.7)"; ctx.font = "600 10px Inter, sans-serif"; ctx.fillText("SAMPLE HISTORY", a.left + 8, a.top + 14);
      ctx.restore();
    },
  };
  function baseOpts(extra = {}) {
    return {
      responsive: true, maintainAspectRatio: false, animation: { duration: 700 },
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#C9DEE2", boxWidth: 10, boxHeight: 10, usePointStyle: true, font: { size: 11.5 } } },
        tooltip: { backgroundColor: "#00202C", borderColor: "rgba(255,255,255,.12)", borderWidth: 1, padding: 10 } },
      scales: {
        x: { ticks: { color: "#8FB0B8", maxRotation: 0, autoSkipPadding: 18, font: { size: 11 } }, grid: { display: false } },
        y: { ticks: { color: "#8FB0B8", font: { size: 11 } }, grid: { color: "rgba(255,255,255,.06)" } },
      },
      ...extra,
    };
  }
  function charts() {
    const d = state.data;
    Chart.register(sampleShade);
    Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    const dates = [...new Set(Object.values(d.price_index).flat().map((p) => p[0]))].sort();
    const labels = dates.map((x) => x);
    state.charts.index = new Chart($("#indexChart"), {
      type: "line",
      data: {
        labels,
        datasets: d.targets.map((t, i) => {
          const m = Object.fromEntries((d.price_index[t.id] || []).map((p) => [p[0], p[1]]));
          return { label: t.name.replace(/^.*· /, ""), data: dates.map((x) => m[x] ?? null), borderColor: PALETTE[i % PALETTE.length],
            backgroundColor: PALETTE[i % PALETTE.length], borderWidth: 2, pointRadius: 0, tension: .25, spanGaps: true };
        }),
      },
      options: baseOpts({ plugins: { ...baseOpts().plugins, sampleShade: { until: d.sample_until } },
        scales: { ...baseOpts().scales, x: { ...baseOpts().scales.x, ticks: { ...baseOpts().scales.x.ticks, callback: (v) => fmtDate(labels[v]) } } } }),
    });
    const dl = d.daily.map((x) => x.date);
    state.charts.daily = new Chart($("#dailyChart"), {
      type: "bar",
      data: { labels: dl, datasets: Object.entries(TYPES).map(([k, t]) => ({ label: t.label, data: d.daily.map((x) => x[k]), backgroundColor: t.color, borderRadius: 3, stack: "s" })) },
      options: baseOpts({ plugins: { ...baseOpts().plugins, sampleShade: { until: d.sample_until } },
        scales: { x: { ...baseOpts().scales.x, stacked: true, ticks: { ...baseOpts().scales.x.ticks, callback: (v) => fmtDate(dl[v]) } }, y: { ...baseOpts().scales.y, stacked: true } } }),
    });
  }

  // ---------- detail dialog ----------
  function openDetail(id) {
    const d = state.data; const p = d.productById[id]; if (!p) return;
    const t = d.targetById[p.target];
    $("#detail-source").textContent = `${t.name} · ${p.category}`;
    $("#detail-title").textContent = p.name;
    const hist = p.history.length ? p.history : [[p.first_seen, p.price]];
    const prices = hist.map((h) => h[1]);
    $("#detail-stats").innerHTML = `<div><b>${money(p.price, p.currency)}</b>current</div>
      <div><b>${money(Math.min(...prices), p.currency)}</b>lowest</div><div><b>${money(Math.max(...prices), p.currency)}</b>highest</div>
      <div><b class="${p.pct_since_first > 0 ? "up" : p.pct_since_first < 0 ? "down" : ""}">${pct(p.pct_since_first) || "0.0%"}</b>since first seen</div>
      <div><b>${p.changes}</b>events</div>`;
    $("#detail-link").href = p.url;
    const dlg = $("#detail");
    if (!dlg.open) dlg.showModal();
    if (!window.Chart) return;
    state.charts.detail?.destroy();
    const last = d.generated_at.slice(0, 10);
    const pts = [...hist]; if (pts[pts.length - 1][0] < last) pts.push([last, pts[pts.length - 1][1]]);
    state.charts.detail = new Chart($("#detailChart"), {
      type: "line",
      data: { labels: pts.map((x) => x[0]), datasets: [{ label: "Price", data: pts.map((x) => x[1]), stepped: true, borderColor: "#04CC9E", backgroundColor: "rgba(4,204,158,.12)", fill: true, pointRadius: 3, pointBackgroundColor: "#04CC9E" }] },
      options: baseOpts({ plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => money(c.parsed.y, p.currency) } } },
        scales: { ...baseOpts().scales, x: { ...baseOpts().scales.x, ticks: { ...baseOpts().scales.x.ticks, callback: (v, i) => fmtDate(pts[i][0]) } } } }),
    });
  }

  init().catch((err) => { console.error(err); $("#updated").textContent = "Could not load data"; });
})();
