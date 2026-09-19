const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const content = $("#content");
const title = $("#title");
const subtitle = $("#subtitle");
const drawer = $("#drawer");
const drawerTitle = $("#drawer-title");
const drawerSubtitle = $("#drawer-subtitle");
const drawerBody = $("#drawer-body");
const drawerActions = $("#drawer-actions");

const PAGES = {
  dashboard: { title: "Overview", subtitle: "Manage inbounds and client configurations." },
  inbounds: { title: "Inbounds", subtitle: "VLESS + WebSocket + TLS entry points on this server." },
  clients: { title: "Clients", subtitle: "Users provisioned across all inbounds." },
  settings: { title: "Settings", subtitle: "Panel name and the public address used to build client links." },
};

let state = { page: "dashboard", inbounds: [], clients: [] };

function toast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = isErr ? "show err" : "show";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.className = ""), 2600);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (res.status === 401) { location.href = "/login"; throw new Error("unauthorized"); }
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}

function fmtBytes(n) {
  if (!n) return "Unlimited";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${u[i]}`;
}
function fmtDate(iso) {
  if (!iso) return "Never";
  const d = new Date(iso);
  if (isNaN(d)) return "Never";
  const days = Math.ceil((d - new Date()) / 86400000);
  const abs = d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  if (days < 0) return `${abs} (expired)`;
  return `${abs} (${days}d left)`;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function badge(on) { return `<span class="badge ${on ? "on" : "off"}">${on ? "Enabled" : "Disabled"}</span>`; }

/* ---------------- navigation ---------------- */
$$(".nav[data-page]").forEach(btn => {
  btn.addEventListener("click", () => go(btn.dataset.page));
});
$("#logout").addEventListener("click", async () => {
  await fetch("/logout", { method: "POST" });
  location.href = "/login";
});

function go(page) {
  state.page = page;
  $$(".nav[data-page]").forEach(b => b.classList.toggle("active", b.dataset.page === page));
  title.textContent = PAGES[page].title;
  subtitle.textContent = PAGES[page].subtitle;
  render();
}

async function render() {
  if (state.page === "dashboard") return renderDashboard();
  if (state.page === "inbounds") return renderInbounds();
  if (state.page === "clients") return renderClients();
  if (state.page === "settings") return renderSettings();
}

/* ---------------- dashboard ---------------- */
async function renderDashboard() {
  content.innerHTML = `<div class="grid-stats" id="stats"></div>
    <div class="panel"><div class="panel-head"><div><h2>Recent inbounds</h2><p>Your most recently created entry points.</p></div>
    <button class="btn primary small" data-go="inbounds">View all</button></div>
    <div id="recent-inbounds"></div></div>`;
  $('[data-go="inbounds"]').addEventListener("click", () => go("inbounds"));
  try {
    const s = await api("/api/summary");
    $("#stats").innerHTML = [
      ["Inbounds", s.inbounds], ["Clients", s.clients], ["Active clients", s.active_clients], ["Transport", s.transport],
    ].map(([l, n]) => `<div class="stat"><div class="n">${esc(n)}</div><div class="l">${esc(l)}</div></div>`).join("");
    const inbounds = await api("/api/inbounds");
    state.inbounds = inbounds;
    const recent = inbounds.slice(0, 5);
    $("#recent-inbounds").innerHTML = recent.length ? `<table><thead><tr><th>Name</th><th>Path</th><th>Port</th><th>Status</th></tr></thead>
      <tbody>${recent.map(i => `<tr><td>${esc(i.name)}</td><td class="mono muted">${esc(i.path)}</td><td class="num">${esc(i.port)}</td><td>${badge(i.enabled)}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty">No inbounds yet. Create one from the Inbounds tab to start issuing client links.</div>`;
  } catch (e) { toast(e.message, true); }
}

/* ---------------- inbounds ---------------- */
async function renderInbounds() {
  content.innerHTML = `<div class="panel"><div class="panel-head"><div><h2>Inbounds</h2><p>Each inbound is one VLESS+WS+TLS endpoint (a WebSocket path) clients connect through.</p></div>
    <button class="btn primary small" id="new-inbound">New inbound</button></div>
    <div id="inbounds-table"></div></div>`;
  $("#new-inbound").addEventListener("click", () => openInboundDrawer());
  try {
    const rows = await api("/api/inbounds");
    state.inbounds = rows;
    $("#inbounds-table").innerHTML = rows.length ? `<table><thead><tr>
      <th>Name</th><th>Path</th><th>Address:Port</th><th>Clients</th><th>Status</th><th></th></tr></thead>
      <tbody>${rows.map(i => `<tr>
        <td>${esc(i.name)}</td>
        <td class="mono muted">${esc(i.path)}</td>
        <td class="mono muted">${esc(i.address || "auto")}:${esc(i.port)}</td>
        <td class="num">${i.client_limit ? `limit ${i.client_limit}` : "unlimited"}</td>
        <td>${badge(i.enabled)}</td>
        <td class="row-actions">
          <button class="btn small ghost" data-edit="${i.id}">Edit</button>
          <button class="btn small danger" data-del="${i.id}">Delete</button>
        </td></tr>`).join("")}</tbody></table>`
      : `<div class="empty">No inbounds yet. Create your first VLESS+WS+TLS entry point.</div>`;
    $$("[data-edit]", content).forEach(b => b.addEventListener("click", () => openInboundDrawer(rows.find(r => r.id === b.dataset.edit))));
    $$("[data-del]", content).forEach(b => b.addEventListener("click", () => deleteInbound(b.dataset.del)));
  } catch (e) { toast(e.message, true); }
}

function openInboundDrawer(existing) {
  const isEdit = !!existing;
  drawerTitle.textContent = isEdit ? "Edit inbound" : "New inbound";
  drawerSubtitle.textContent = "VLESS over WebSocket, behind TLS.";
  drawerBody.innerHTML = `
    <label>Name<input id="f-name" value="${esc(existing?.name || "")}" placeholder="Main inbound"></label>
    <div class="field-row">
      <label>Port<input id="f-port" type="number" value="${existing?.port || 443}"></label>
      <label>WebSocket path<input id="f-path" value="${esc(existing?.path || "")}" placeholder="auto-generated"></label>
    </div>
    <div class="field-row">
      <label>Address (optional)<input id="f-address" value="${esc(existing?.address || "")}" placeholder="server IP / hostname"></label>
      <label>Client limit<input id="f-client_limit" type="number" value="${existing?.client_limit || 0}"></label>
    </div>
    <div class="field-row">
      <label>Host header<input id="f-host" value="${esc(existing?.host_header || "")}" placeholder="your domain"></label>
      <label>SNI<input id="f-sni" value="${esc(existing?.sni || "")}" placeholder="defaults to host"></label>
    </div>
    <label>Note<input id="f-note" value="${esc(existing?.note || "")}" placeholder="optional"></label>
    ${isEdit ? `<label style="display:flex;align-items:center;gap:8px;flex-direction:row"><input id="f-enabled" type="checkbox" style="width:auto" ${existing.enabled ? "checked" : ""}> Enabled</label>` : `<p class="hint">Protocol is fixed to VLESS / WebSocket / TLS for this deployment.</p>`}
  `;
  drawerActions.innerHTML = `<button class="btn ghost" id="d-cancel">Cancel</button><button class="btn primary" id="d-save">${isEdit ? "Save changes" : "Create inbound"}</button>`;
  $("#d-cancel").addEventListener("click", closeDrawer);
  $("#d-save").addEventListener("click", async () => {
    const body = {
      name: $("#f-name").value, port: Number($("#f-port").value) || 443,
      path: $("#f-path").value, address: $("#f-address").value,
      client_limit: Number($("#f-client_limit").value) || 0,
      host_header: $("#f-host").value, sni: $("#f-sni").value, note: $("#f-note").value,
      protocol: "vless", network: "ws", security: "tls",
    };
    if (isEdit) body.enabled = $("#f-enabled").checked;
    try {
      if (isEdit) await api(`/api/inbounds/${existing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      else await api("/api/inbounds", { method: "POST", body: JSON.stringify(body) });
      toast(isEdit ? "Inbound updated" : "Inbound created");
      closeDrawer(); renderInbounds();
    } catch (e) { toast(e.message, true); }
  });
  openDrawer();
}

async function deleteInbound(id) {
  if (!confirm("Delete this inbound and all its clients? This cannot be undone.")) return;
  try { await api(`/api/inbounds/${id}`, { method: "DELETE" }); toast("Inbound deleted"); renderInbounds(); }
  catch (e) { toast(e.message, true); }
}

/* ---------------- clients ---------------- */
async function renderClients() {
  content.innerHTML = `<div class="panel"><div class="panel-head"><div><h2>Clients</h2><p>Each client gets a unique UUID and a ready-to-use VLESS link.</p></div>
    <button class="btn primary small" id="new-client">New client</button></div>
    <div id="clients-table"></div></div>`;
  try {
    const [inbounds, rows] = await Promise.all([api("/api/inbounds"), api("/api/clients")]);
    state.inbounds = inbounds; state.clients = rows;
    if (!inbounds.length) {
      $("#clients-table").innerHTML = `<div class="empty">Create an inbound first, then add clients to it.</div>`;
    } else {
      $("#clients-table").innerHTML = rows.length ? `<table><thead><tr>
        <th>Name</th><th>Inbound</th><th>Link</th><th>Data limit</th><th>Expires</th><th>Status</th><th></th></tr></thead>
        <tbody>${rows.map(c => `<tr>
          <td>${esc(c.name)}</td>
          <td class="muted">${esc(c.inbound_name || "—")}</td>
          <td><div class="link-cell"><code>${esc(c.link || "")}</code><button class="btn small ghost" data-copy="${esc(c.link || "")}">Copy</button></div></td>
          <td class="num">${fmtBytes(c.limit_bytes)}</td>
          <td class="muted">${fmtDate(c.expires_at)}</td>
          <td>${badge(c.enabled)}</td>
          <td class="row-actions">
            <button class="btn small ghost" data-regen="${c.id}">New UUID</button>
            <button class="btn small ghost" data-edit="${c.id}">Edit</button>
            <button class="btn small danger" data-del="${c.id}">Delete</button>
          </td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">No clients yet. Add one to generate a VLESS link.</div>`;
      $$("[data-copy]", content).forEach(b => b.addEventListener("click", () => copyLink(b.dataset.copy)));
      $$("[data-edit]", content).forEach(b => b.addEventListener("click", () => openClientDrawer(rows.find(r => r.id === b.dataset.edit))));
      $$("[data-del]", content).forEach(b => b.addEventListener("click", () => deleteClient(b.dataset.del)));
      $$("[data-regen]", content).forEach(b => b.addEventListener("click", () => regenClient(b.dataset.regen)));
    }
    $("#new-client").addEventListener("click", () => openClientDrawer(null, inbounds));
  } catch (e) { toast(e.message, true); }
}

function daysRemaining(iso) {
  if (!iso) return 0;
  const d = new Date(iso);
  if (isNaN(d)) return 0;
  return Math.max(0, Math.ceil((d - new Date()) / 86400000));
}

function copyLink(link) {
  if (!link) return;
  navigator.clipboard?.writeText(link).then(() => toast("Link copied")).catch(() => toast("Could not copy link", true));
}

function openClientDrawer(existing, inbounds) {
  const isEdit = !!existing;
  const list = inbounds || state.inbounds;
  drawerTitle.textContent = isEdit ? "Edit client" : "New client";
  drawerSubtitle.textContent = isEdit ? existing.inbound_name : "Assign to an inbound and set optional limits.";
  const inboundOptions = list.map(i => `<option value="${i.id}" ${existing?.inbound_id === i.id ? "selected" : ""}>${esc(i.name)}</option>`).join("");
  drawerBody.innerHTML = `
    ${isEdit ? "" : `<label>Inbound<select id="f-inbound" style="width:100%;padding:9px 11px;background:var(--surface-2);border:1px solid var(--border);border-radius:8px;color:var(--text)">${inboundOptions}</select></label>`}
    <label>Name<input id="f-name" value="${esc(existing?.name || "")}" placeholder="Client name"></label>
    <div class="field-row">
      <label>Data limit (GB, 0 = unlimited)<input id="f-limit_gb" type="number" step="0.1" value="${existing ? (existing.limit_bytes / 1024 ** 3).toFixed(2) : 0}"></label>
      <label>Expires in (days, 0 = never)<input id="f-expires_days" type="number" value="${daysRemaining(existing?.expires_at)}"></label>
    </div>
    <div class="field-row">
      <label>IP limit<input id="f-ip_limit" type="number" value="${existing?.ip_limit || 0}"></label>
      <label>Connection limit<input id="f-connection_limit" type="number" value="${existing?.connection_limit || 0}"></label>
    </div>
    <label>Note<input id="f-note" value="${esc(existing?.note || "")}" placeholder="optional"></label>
    ${isEdit ? `<label style="display:flex;align-items:center;gap:8px;flex-direction:row"><input id="f-enabled" type="checkbox" style="width:auto" ${existing.enabled ? "checked" : ""}> Enabled</label>` : ""}
  `;
  drawerActions.innerHTML = `<button class="btn ghost" id="d-cancel">Cancel</button><button class="btn primary" id="d-save">${isEdit ? "Save changes" : "Create client"}</button>`;
  $("#d-cancel").addEventListener("click", closeDrawer);
  $("#d-save").addEventListener("click", async () => {
    const body = {
      name: $("#f-name").value,
      limit_gb: Number($("#f-limit_gb").value) || 0,
      expires_days: Number($("#f-expires_days").value) || 0,
      ip_limit: Number($("#f-ip_limit").value) || 0,
      connection_limit: Number($("#f-connection_limit").value) || 0,
      note: $("#f-note").value,
    };
    if (isEdit) body.enabled = $("#f-enabled").checked;
    else body.inbound_id = $("#f-inbound").value;
    try {
      if (isEdit) await api(`/api/clients/${existing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      else await api("/api/clients", { method: "POST", body: JSON.stringify(body) });
      toast(isEdit ? "Client updated" : "Client created");
      closeDrawer(); renderClients();
    } catch (e) { toast(e.message, true); }
  });
  openDrawer();
}

async function deleteClient(id) {
  if (!confirm("Delete this client? Their link will stop working immediately.")) return;
  try { await api(`/api/clients/${id}`, { method: "DELETE" }); toast("Client deleted"); renderClients(); }
  catch (e) { toast(e.message, true); }
}
async function regenClient(id) {
  if (!confirm("Generate a new UUID for this client? Their old link will stop working.")) return;
  try { await api(`/api/clients/${id}/regenerate`, { method: "POST" }); toast("New UUID generated"); renderClients(); }
  catch (e) { toast(e.message, true); }
}

/* ---------------- settings ---------------- */
async function renderSettings() {
  content.innerHTML = `<div class="panel"><div class="panel-head"><div><h2>Panel settings</h2><p>Controls branding and the address used when building client links.</p></div></div>
    <div style="padding:18px">
      <label>Panel name<input id="s-name"></label>
      <label>Public base URL<input id="s-url" placeholder="https://your-domain.com"></label>
      <p class="hint">Leave the public base URL empty to fall back to the request's Host header when building VLESS links.</p>
      <button class="btn primary" id="s-save">Save settings</button>
    </div></div>`;
  try {
    const s = await api("/api/settings");
    $("#s-name").value = s.panel_name || "";
    $("#s-url").value = s.public_base_url || "";
    $("#s-save").addEventListener("click", async () => {
      try {
        await api("/api/settings", { method: "PATCH", body: JSON.stringify({ panel_name: $("#s-name").value, public_base_url: $("#s-url").value }) });
        toast("Settings saved");
      } catch (e) { toast(e.message, true); }
    });
  } catch (e) { toast(e.message, true); }
}

/* ---------------- drawer ---------------- */
function openDrawer() { drawer.classList.remove("hidden"); }
function closeDrawer() { drawer.classList.add("hidden"); drawerBody.innerHTML = ""; drawerActions.innerHTML = ""; }
$("#drawer-close").addEventListener("click", closeDrawer);
drawer.addEventListener("click", e => { if (e.target === drawer) closeDrawer(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });

go("dashboard");
