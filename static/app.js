const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => "$" + (n || 0).toFixed(4);
const num = (n) => (n || 0).toLocaleString();
const usd = (n) => "$" + (n < 0.1 ? n.toFixed(3) : n.toFixed(2));

let sid = localStorage.getItem("studfinder_sid");
if (!sid) { sid = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()).slice(0, 36); localStorage.setItem("studfinder_sid", sid); }

const EXAMPLES = {
  storefront: "A small coffee shop storefront for my LEGO town: sand green walls with white trim, big front windows, a door in the middle, a red and white striped awning, and a sign above the door. About 16 studs wide.",
  bakery: "A corner bakery with dark tan brick walls, a dark red door, two arched windows, a little bench out front, and flower boxes under the windows. Minifigure scale, about 16 by 16 studs.",
  bookshop: "A tiny narrow bookshop, 8 studs wide and two stories tall. Dark blue walls, white window frames, a shop window full of books, and a small sign hanging over the door.",
};
const STATUS = {
  starting: "Starting up…",
  finder: "Finder is searching the LEGO catalog and building your list…",
  checker: "Checker is reviewing the list for rare parts and missing pieces…",
  refiner: "Refiner is updating your list…",
};

let polling = null;
let last = null;
const EMPTY_PARTS = $("parts").innerHTML;

async function api(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sid, ...body }) } : {};
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 2600);
}

function render(s) {
  last = s;
  const running = !!s.running;
  $("findBtn").disabled = running;
  $("chatInput").disabled = running || !s.items.length;
  $("chatBtn").disabled = running || !s.items.length;
  if (s.description && !$("desc").value) { $("desc").value = s.description; updateCount(); }

  // status + errors
  $("status").hidden = !running;
  if (running) $("status").innerHTML = `<span class="studs"><i></i><i></i><i></i></span>${esc(STATUS[s.running] || "Working…")}`;
  $("errorBox").hidden = !s.error; $("errorBox").textContent = s.error || "";
  ["finder", "checker", "refiner"].forEach((a) => $("pill-" + a).classList.toggle("active", s.running === a));

  // summary + notes
  $("summary").hidden = !s.summary;
  $("summary").innerHTML = s.summary ? `<b>Finder</b>${esc(s.summary)}` : "";
  $("notes").hidden = !s.checker_notes.length;
  $("notes").innerHTML = s.checker_notes.length ? `<b>Checker notes</b><ul>${s.checker_notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : "";

  // totals
  const rare = s.items.filter((i) => i.rarity !== "common").length;
  const est = s.estimate || {};
  $("totals").innerHTML = s.items.length
    ? `<span class="tot">${s.items.length} parts</span><span class="tot">${num(s.total_pieces)} pieces</span>${rare ? `<span class="tot">${rare} hard to find</span>` : ""}`
      + (est.priced ? `<span class="tot money" title="BrickLink estimate for ${est.priced} of ${est.parts} parts">≈ $${est.total.toFixed(2)}${est.priced < est.parts ? "*" : ""} est.</span>` : "")
    : "";
  $("priceNote").textContent = est.priced
    ? `Price estimates: average price new parts sold for on BrickLink over the last 6 months (snapshot ${est.date}), not including shipping.`
      + (est.priced < est.parts ? ` *${est.parts - est.priced} part${est.parts - est.priced > 1 ? "s have" : " has"} no price yet and ${est.parts - est.priced > 1 ? "aren't" : "isn't"} in the total.` : "")
    : "";

  renderParts(s);
  renderChat(s);
  renderTrace(s);
  renderMeters(s);
  renderSafety(s);

  $("exportBar").hidden = !s.items.length;
  $("downloadBtn").href = `/api/export.xml?session_id=${encodeURIComponent(sid)}`;
  $("skippedNote").hidden = !s.export_skipped.length;
  $("skippedNote").textContent = s.export_skipped.length ? `Not in the file (no BrickLink color match): ${s.export_skipped.join("; ")}` : "";

  if (running && !polling) polling = setInterval(refresh, 800);
  if (!running && polling) { clearInterval(polling); polling = null; }
}

function renderParts(s) {
  if (!s.items.length) { $("parts").innerHTML = EMPTY_PARTS; return; }
  const groups = {};
  s.items.forEach((i) => (groups[i.section] = groups[i.section] || []).push(i));
  const locked = s.running ? "disabled" : "";
  $("parts").innerHTML = Object.entries(groups).map(([sec, items]) => `
    <div class="section-title">${esc(sec)}</div>
    ${items.map((i) => `
      <div class="item" data-id="${i.id}">
        ${i.img ? `<img src="${esc(i.img)}" alt="${esc(i.name)}" loading="lazy">` : `<div class="thumb"></div>`}
        <div>
          <div class="name">${esc(i.name)}</div>
          <div class="meta">
            <span class="pn">${esc(i.part_num)}</span>
            <span class="color"><span class="swatch" style="background:#${esc(i.rgb)}"></span>${esc(i.color)}</span>
            <span class="badge ${esc(i.rarity)}" title="Appears in ${i.sets} official sets; last made ${i.last_year}">${esc(i.rarity)} · ${i.sets} sets · ${i.last_year}</span>
            ${i.price_each != null ? `<span class="price" title="BrickLink 6-month average, new">≈ ${usd(i.price_each)} each · ${usd(i.price_each * i.qty)}${i.price_few_sales ? ` <span class="muted" title="Based on fewer than 10 sales">(few sales)</span>` : ""}</span>` : `<span class="muted">no price yet</span>`}
          </div>
        </div>
        <div class="row gap">
          <div class="qty">
            <button data-act="dec" ${locked} aria-label="Fewer">−</button>
            <input type="number" min="0" max="300" value="${i.qty}" data-act="set" ${locked} aria-label="Quantity">
            <button data-act="inc" ${locked} aria-label="More">+</button>
          </div>
          <button class="remove" data-act="remove" ${locked} title="Remove" aria-label="Remove">✕</button>
        </div>
        ${i.suggestion ? `
          <div class="swap">
            ${i.suggestion.img ? `<img src="${esc(i.suggestion.img)}" alt="">` : ""}
            <div class="grow"><b>Checker suggests:</b> ${esc(i.suggestion.name)} in
              <span class="color"><span class="swatch" style="background:#${esc(i.suggestion.rgb)}"></span>${esc(i.suggestion.color)}</span>
              (${i.suggestion.sets} sets${i.suggestion.price_each != null ? `, ≈ ${usd(i.suggestion.price_each)} each` : ""}). <span class="muted">${esc(i.suggestion.reason)}</span></div>
            <button class="btn blue small" data-act="swap" ${locked}>Swap</button>
          </div>` : ""}
      </div>`).join("")}
  `).join("");
}

function renderChat(s) {
  const log = $("chatlog");
  if (!s.chat.length) return;
  log.innerHTML = s.chat.map((m) => `<div class="msg ${m.role === "user" ? "user" : "agent"}">${esc(m.text)}</div>`).join("");
  log.scrollTop = log.scrollHeight;
}

function renderTrace(s) {
  const el = $("trace");
  if (!s.trace.length) { el.innerHTML = `<li class="muted small">Nothing yet.</li>`; return; }
  const name = (a) => a[0].toUpperCase() + a.slice(1);
  el.innerHTML = s.trace.map((t) => {
    const who = `<span class="who ${t.agent}">${name(t.agent)}</span>`;
    if (t.kind === "tool") return `<li>${who}${esc(t.tool)} <code>${esc(t.args)}</code>${t.ok ? "" : `<br><span class="bad">✕ ${esc(t.result)}</span>`}</li>`;
    if (t.kind === "limit") return `<li>${who}<span class="bad">${esc(t.text)}</span></li>`;
    return `<li>${who}<span class="muted">${esc(t.text || "(done)")}</span></li>`;
  }).join("");
  el.scrollTop = el.scrollHeight;
}

function renderMeters(s) {
  const u = s.run_usage;
  if (u && u.calls) {
    const agents = Object.entries(u.by_agent || {}).map(([a, v]) => `${a} ${money(v.cost)} (${v.calls} calls)`).join(" · ");
    $("runMeter").innerHTML = `
      <div class="cost-big">${money(u.cost)}</div>
      <table>
        <tr><td>Input tokens</td><td>${num(u.input)}</td></tr>
        <tr><td>&nbsp;&nbsp;of which cached</td><td>${num(u.cached)} (${u.input ? Math.round((100 * u.cached) / u.input) : 0}%)</td></tr>
        <tr><td>Output tokens</td><td>${num(u.output)}</td></tr>
        <tr><td>Model calls</td><td>${u.calls}</td></tr>
        ${u.cache_hits ? `<tr><td>Served free from cache</td><td>${u.cache_hits} of ${u.calls}</td></tr>` : ""}
      </table>
      <p class="muted small">${esc(agents)}</p>`;
  }
  const su = s.session_usage || {};
  $("sessionMeter").innerHTML = `<b>${money(su.cost)}</b> <span class="muted small">· ${num((su.input || 0) + (su.output || 0))} tokens · ${su.calls || 0} calls</span>`;
  const pct = Math.min(100, (100 * s.budget.used) / s.budget.session_limit);
  $("budgetFill").style.width = pct + "%";
  $("budgetFill").style.background = pct > 85 ? "var(--red)" : pct > 60 ? "var(--yellow)" : "var(--green)";
  $("budgetText").textContent = `${pct.toFixed(1)}% of this session's ${num(s.budget.session_limit)}-token budget`;
}

function renderSafety(s) {
  $("safety").innerHTML = s.blocked.length
    ? s.blocked.slice().reverse().map((b) => `<li><b>${esc(b.kind)}</b> · ${esc(b.detail)} <span class="muted">${esc(b.t)}</span></li>`).join("")
    : `<li class="muted small">Nothing blocked yet.</li>`;
}

async function refresh() {
  try { render(await api(`/api/state?session_id=${encodeURIComponent(sid)}`)); } catch (e) { /* keep polling */ }
}

function updateCount() { $("descCount").textContent = `${$("desc").value.length} / 1500`; }

$("desc").addEventListener("input", updateCount);
document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => {
  $("desc").value = EXAMPLES[b.dataset.example]; updateCount(); $("desc").focus();
}));

$("findBtn").addEventListener("click", async () => {
  const description = $("desc").value.trim();
  if (!description) { toast("Describe your build first."); $("desc").focus(); return; }
  try { render(await api("/api/find", { description })); } catch (e) { toast(e.message); }
});

$("chatForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const message = $("chatInput").value.trim();
  if (!message) return;
  $("chatInput").value = "";
  try { render(await api("/api/chat", { message })); } catch (e) { toast(e.message); }
});

$("parts").addEventListener("click", async (ev) => {
  const btn = ev.target.closest("[data-act]");
  if (!btn || btn.tagName === "INPUT") return;
  const row = btn.closest(".item"); const id = +row.dataset.id;
  const item = last.items.find((i) => i.id === id);
  const act = btn.dataset.act;
  try {
    if (act === "inc" || act === "dec") render(await api("/api/edit", { item_id: id, action: "qty", qty: item.qty + (act === "inc" ? 1 : -1) }));
    if (act === "remove") render(await api("/api/edit", { item_id: id, action: "remove" }));
    if (act === "swap") { render(await api("/api/edit", { item_id: id, action: "swap" })); toast("Swapped."); }
  } catch (e) { toast(e.message); }
});
$("parts").addEventListener("change", async (ev) => {
  if (ev.target.dataset.act !== "set") return;
  const id = +ev.target.closest(".item").dataset.id;
  try { render(await api("/api/edit", { item_id: id, action: "qty", qty: Math.max(0, +ev.target.value || 0) })); } catch (e) { toast(e.message); refresh(); }
});

$("copyBtn").addEventListener("click", async () => {
  const xml = await (await fetch(`/api/export.xml?session_id=${encodeURIComponent(sid)}`)).text();
  try { await navigator.clipboard.writeText(xml); toast("Copied. On BrickLink, paste it into the 'Upload BrickLink XML format' tab."); }
  catch { toast("Copy failed. Use Download instead."); }
});

$("resetBtn").addEventListener("click", async () => {
  if (!confirm("Clear your parts list and chat?")) return;
  await api("/api/reset", { message: "" });
  location.reload();
});

refresh();
