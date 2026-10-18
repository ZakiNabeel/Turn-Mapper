/* TURN Studio front end: plain JS, no build step. Talks to the local FastAPI server (/api/...). */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const SVGNS = "http://www.w3.org/2000/svg";

const S = {
  info: null, project: null, pid: null, fid: null, rec: null, fd: null,
  w: 0, h: 0, view: { x: 0, y: 0, k: 1 }, tab: "run", tool: null, paintCls: 1,
  sel: null, undo: [], draft: [], pairs: [], layers: {}, saveTimer: null, busy: false,
  maskLoaded: false, maskDirty: false, eraseDirty: false,
};

// ---------------------------------------------------------------- helpers
async function api(path, opt = {}) {
  const init = { method: opt.method || "GET", headers: {} };
  if (opt.json !== undefined) { init.body = JSON.stringify(opt.json); init.headers["Content-Type"] = "application/json"; }
  if (opt.form) init.body = opt.form;
  const r = await fetch(path, init);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) { /* not json */ }
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r;
}
function status(msg, busy = false) { const el = $("#status"); el.textContent = msg; el.classList.toggle("busy", busy); }
async function task(label, fn) {
  if (S.busy) return;
  S.busy = true; status(label + "…", true);
  try { const r = await fn(); status(label + ": done."); return r; }
  catch (e) { status(label + " failed: " + e.message); alert(label + " failed:\n" + e.message); }
  finally { S.busy = false; }
}
const P = () => `/api/projects/${encodeURIComponent(S.pid)}`;
const F = () => `${P()}/floors/${encodeURIComponent(S.fid)}`;
const sc = () => (S.fd ? S.fd.transform.scale_m_per_px : 1);
const toPx = (m) => m / sc();
const el = (tag, attrs = {}, parent) => {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
};
const h = (tag, attrs = {}, html = "") => { const e = document.createElement(tag); Object.assign(e, attrs); if (html) e.innerHTML = html; return e; };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const uid = (prefix, list) => { let i = list.length + 1; const ids = new Set(list.map((x) => x.id)); while (ids.has(prefix + i)) i++; return prefix + i; };
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

document.addEventListener("DOMContentLoaded", () => {
  const b = $("#addLink"); if (!b) return;
  b.onclick = async () => {
    const [fa, na, ta] = ($("#linkA").value || "").split(":"), [fb, nb] = ($("#linkB").value || "").split(":");
    if (!fa || !fb || (fa === fb)) { status("Pick nodes on two different floors."); return; }
    const manual = [...((S.links && S.links.manual) || []), { from: { floor_id: fa, node_id: na }, to: { floor_id: fb, node_id: nb }, type: ta }];
    await api(`${P()}/links`, { method: "PUT", json: { manual } }); renderLinks();
  };
});

// ---------------------------------------------------------------- projects & files
async function loadInfo() {
  S.info = await api("/api/info");
  const learned = S.info.segmenters.learned;
  for (const v of ["learned", "hybrid"]) {
    const opt = $(`#segSel option[value="${v}"]`); if (!opt) continue;
    opt.disabled = !learned.available;
    if (!learned.available) opt.textContent = v + " (unavailable: " + learned.detail + ")";
  }
  $("#fileInput").accept = S.info.accept;
  const o = S.info.ocr, b = $("#ocrBadge");
  if (o && b) {
    b.textContent = o.available ? `Labels: ${o.engine}` : "Labels: OFF";
    b.className = "badge " + (o.available ? "ok" : "err"); b.title = o.detail;
    if (!o.available) status("Room labels are OFF: " + o.detail);
  }
}
async function loadProjects(selectId) {
  const list = await api("/api/projects");
  const sel = $("#projectSel");
  sel.innerHTML = list.length ? "" : '<option value="">— none —</option>';
  for (const p of list) sel.appendChild(h("option", { value: p.id, textContent: `${p.name} (${p.floors} floors)` }));
  const want = selectId || localStorage.getItem("turn.pid") || (list[0] && list[0].id);
  if (want && list.some((p) => p.id === want)) { sel.value = want; await openProject(want); }
}
async function openProject(pid) {
  S.pid = pid; localStorage.setItem("turn.pid", pid);
  S.project = await api(P());
  $("#uploadBtn").disabled = false; $("#exportBtn").disabled = !S.project.floors.length;
  renderFiles(); renderFloors();
  const last = localStorage.getItem("turn.fid." + pid);
  const f = S.project.floors.find((x) => x.id === last) || S.project.floors[0];
  if (f) await openFloor(f.id); else clearFloor();
}
function renderFiles() {
  const ul = $("#fileList"); ul.innerHTML = "";
  if (!S.project.files.length) { ul.innerHTML = '<li class="empty">Upload a floor plan: PDF (scanned or vector), PNG/JPG, DXF or SVG.</li>'; return; }
  for (const f of S.project.files) {
    const li = h("li", {}, `<b>${esc(f.name)}</b> <span class="badge">${esc(f.kind)}</span><br><span class="sub">click to add a floor</span>`);
    li.onclick = () => openAddFloor(f.name);
    ul.appendChild(li);
  }
}
function renderFloors() {
  const opt = $(`#projectSel option[value="${CSS.escape(S.pid || "")}"]`);
  if (opt && S.project) opt.textContent = `${S.project.name} (${S.project.floors.length} floor${S.project.floors.length === 1 ? "" : "s"})`;
  const ul = $("#floorList"); ul.innerHTML = "";
  if (!S.project.floors.length) { ul.innerHTML = '<li class="empty">No floors yet. Click a file above to add one.</li>'; return; }
  for (const f of S.project.floors) {
    const s = f.summary;
    const badge = !s ? '<span class="badge">not run</span>'
      : s.passed ? '<span class="badge ok">valid</span>' : '<span class="badge err">errors</span>';
    const ed = f.status === "edited" || f.status === "corrected" ? `<span class="badge edit">${f.status}</span>` : "";
    const sub = s ? `${s.rooms} rooms · ${s.doors} doors · ${s.pois} places · ${s.components} graph part${s.components === 1 ? "" : "s"}` : esc(f.source);
    const li = h("li", { className: f.id === S.fid ? "on" : "" },
      `<button class="act ghost" title="Remove floor">✕</button><b>${esc(f.id)}</b> ${badge}${ed}<br><span class="sub">${esc(f.name)}</span><br><span class="sub">${sub}</span>`);
    li.onclick = (e) => { if (e.target.classList.contains("act")) return; openFloor(f.id); };
    $(".act", li).onclick = async () => {
      if (!confirm(`Remove floor ${f.id} from the project?`)) return;
      await api(`${P()}/floors/${encodeURIComponent(f.id)}`, { method: "DELETE" });
      if (S.fid === f.id) { S.fid = null; clearFloor(); }
      await openProject(S.pid);
    };
    ul.appendChild(li);
  }
}

// add-floor dialog
let dlgState = {};
async function openAddFloor(name) {
  const info = await task("Reading " + name, () => api(`${P()}/files/${encodeURIComponent(name)}`));
  if (!info) return;
  dlgState = { name, info, page: null, image_index: null };
  $("#dlgFile").textContent = name;
  const pp = $("#pagePicker"); pp.innerHTML = "";
  const items = [];
  for (const pg of info.pages) {
    if (info.kind === "pdf" && pg.images.length && pg.branch !== "vector") {
      pg.images.forEach((im) => items.push({ page: pg.page, image_index: im.index, label: `page ${pg.page} · image ${im.index + 1} (${im.width}×${im.height})` }));
    }
    items.push({ page: pg.page, image_index: null, label: info.kind === "pdf" ? `page ${pg.page} · whole page${pg.branch === "vector" ? " (vector)" : ""}` : info.kind });
  }
  for (const it of items) {
    const q = `?page=${it.page}` + (it.image_index !== null ? `&image_index=${it.image_index}` : "");
    const d = h("div", { className: "pg" }, `<img loading="lazy" src="${P()}/files/${encodeURIComponent(name)}/thumb${q}" alt=""><div>${esc(it.label)}</div>`);
    d.onclick = () => { $$(".pg", pp).forEach((x) => x.classList.remove("on")); d.classList.add("on"); dlgState.page = it.page; dlgState.image_index = it.image_index; };
    pp.appendChild(d);
  }
  if (items.length === 1) pp.firstChild.click();
  const f = $("#addFloorForm");
  f.id.value = uid("F", S.project.floors); f.name.value = "";
  $("#vectorOpts").hidden = !(info.kind === "svg" || (info.kind === "pdf" && info.pages.some((p) => p.branch === "vector")));
  $("#dxfOpts").hidden = info.kind !== "dxf";
  if (info.kind === "dxf") {
    $("#dxfLayers").innerHTML = info.layers.map((l) => `<label><input type="checkbox" value="${esc(l.name)}" ${l.default_on ? "checked" : ""}> ${esc(l.name)} <span class="sub">(${l.entities})</span></label>`).join("");
  }
  $("#addFloorDlg").showModal();
}
$("#addFloorForm").addEventListener("submit", async (e) => {
  if (e.submitter && e.submitter.value === "cancel") return;
  e.preventDefault();
  const f = e.target;
  if (dlgState.page === null) { alert("Pick a page or image first."); return; }
  const options = {};
  if (!$("#vectorOpts").hidden && f.drawing_scale.value) options.drawing_scale = Number(f.drawing_scale.value);
  if (!$("#dxfOpts").hidden) {
    options.layers_include = $$("#dxfLayers input:checked").map((x) => x.value);
    if (f.units.value) options.units = f.units.value;
  }
  const body = { source: dlgState.name, page: dlgState.page, image_index: dlgState.image_index, id: f.id.value,
    building: f.building.value, level: Number(f.level.value), name: f.name.value || f.id.value, options };
  const rec = await task("Adding floor " + body.id, () => api(`${P()}/floors`, { method: "POST", json: body }));
  if (!rec) return;
  $("#addFloorDlg").close();
  S.project = await api(P()); renderFloors(); $("#exportBtn").disabled = false;
  await openFloor(rec.id);
});

// ---------------------------------------------------------------- floor
function clearFloor() {
  S.fid = null; S.rec = null; S.fd = null;
  $("#planImg").removeAttribute("src"); $("#ov").innerHTML = "";
  $("#hint").textContent = S.pid ? "Click a file to add a floor, or pick a floor on the left." : "Create a project to start.";
  $("#hint").hidden = false; $("#runBtn").disabled = true;
  renderPanels();
}
async function openFloor(fid) {
  S.fid = fid; localStorage.setItem("turn.fid." + S.pid, fid);
  const r = await api(F());
  S.rec = r.record; S.fd = r.floor; S.sel = null; S.undo = []; S.draft = []; S.pairs = [];
  S.maskLoaded = false; S.maskDirty = false; S.eraseDirty = false;
  $("#segSel").value = S.rec.segmenter || "classical";
  await loadPlanImage();
  renderFloors(); renderPanels(); render();
}
function loadPlanImage() {
  return new Promise((resolve) => {
    const img = $("#planImg");
    img.onload = () => {
      S.w = img.naturalWidth; S.h = img.naturalHeight;
      for (const c of [$("#maskCanvas"), $("#eraseCanvas")]) { c.width = S.w; c.height = S.h; }
      $("#ov").setAttribute("width", S.w); $("#ov").setAttribute("height", S.h); $("#ov").setAttribute("viewBox", `0 0 ${S.w} ${S.h}`);
      loadErase();
      if (S.layers.masks || S.tab === "input") loadMasks();
      fit(); resolve();
    };
    img.src = `${F()}/image/base?t=${Date.now()}`;
    $("#hint").hidden = true;
  });
}
async function loadMasks() {
  if (!S.fd) return;
  const c = $("#maskCanvas"), ctx = c.getContext("2d");
  const img = new Image();
  await new Promise((res) => { img.onload = res; img.onerror = res; img.src = `${F()}/image/masks?t=${Date.now()}`; });
  ctx.clearRect(0, 0, c.width, c.height);
  if (img.naturalWidth) { ctx.drawImage(img, 0, 0); S.maskLoaded = true; }
}
async function loadErase() {
  const c = $("#eraseCanvas"), ctx = c.getContext("2d");
  ctx.clearRect(0, 0, c.width, c.height);
  const img = new Image();
  const r = await fetch(`${F()}/image/erase?t=${Date.now()}`);
  if (r.status !== 200) return;
  const url = URL.createObjectURL(await r.blob());
  await new Promise((res) => { img.onload = res; img.onerror = res; img.src = url; });
  URL.revokeObjectURL(url);
  if (!img.naturalWidth) return;
  const tmp = h("canvas"); tmp.width = img.naturalWidth; tmp.height = img.naturalHeight;
  const t = tmp.getContext("2d"); t.drawImage(img, 0, 0);
  const d = t.getImageData(0, 0, tmp.width, tmp.height);
  for (let i = 0; i < d.data.length; i += 4) { const on = d.data[i] > 127; d.data[i] = 255; d.data[i + 1] = 40; d.data[i + 2] = 40; d.data[i + 3] = on ? 255 : 0; }
  ctx.putImageData(d, 0, 0);
}

// ---------------------------------------------------------------- panels
function kv(rows) { return '<div class="kv">' + rows.map(([k, v]) => `<span>${k}</span><b>${v}</b>`).join("") + "</div>"; }
function renderPanels() {
  const has = !!S.rec;
  $("#runBtn").disabled = !has; $("#revertBtn").disabled = !S.fd; $("#rerunMasks").disabled = !S.fd;
  $("#floorMeta").innerHTML = has ? `<div class="grid">
      <label class="fld">Name <input id="mName" value="${esc(S.rec.name)}"></label>
      <label class="fld">Building <input id="mBuilding" value="${esc(S.rec.building)}"></label>
      <label class="fld">Level <input id="mLevel" type="number" value="${S.rec.level}"></label>
      <label class="fld">Source <input value="${esc(S.rec.source)}${S.rec.page ? " p." + S.rec.page : ""}" disabled></label></div>` : "No floor open.";
  if (has) for (const [id, key] of [["#mName", "name"], ["#mBuilding", "building"], ["#mLevel", "level"]]) {
    $(id).onchange = async (e) => { S.rec = await api(F(), { method: "PATCH", json: { [key]: e.target.value } }); S.project = await api(P()); renderFloors(); };
  }
  const s = S.rec && S.rec.summary;
  const meta = (S.rec && S.rec.source_meta) || {};
  $("#summary").innerHTML = !s ? (has ? '<p class="note">Not run yet. Press <b>Run automatic mapping</b>.</p>' : "") : kv([
    ["Validation", s.passed ? '<span class="badge ok">passes</span>' : '<span class="badge err">fails</span>'],
    ["Rooms / doors", `${s.rooms} / ${s.doors}`], ["Graph", `${s.nodes} nodes, ${s.edges} edges, ${s.components} part(s)`],
    ["Places (POIs)", s.pois], ["Sample routes", `${s.routes_ok}/${s.routes_tried} found`],
    ["Scale", `${(s.scale_m_per_px * 100).toFixed(2)} cm/px (${s.scale_source})`],
    ["Input", `${meta.adapter || "?"}${meta.units ? " · units " + meta.units : ""}`],
    ["Run time", S.rec.stats && S.rec.stats.seconds ? S.rec.stats.seconds + " s" : "–"],
  ]);
  $("#scaleNow").innerHTML = s ? kv([["Current", `${(s.scale_m_per_px * 100).toFixed(3)} cm/px`], ["Source", s.scale_source]]) : "Run the floor first.";
  renderPairs(); renderChecks(); renderProps(); renderLinks();
}
function renderPairs() {
  const ul = $("#pairList"); ul.innerHTML = "";
  S.pairs.forEach((p, i) => {
    const px = dist(p.p1_px, p.p2_px);
    const li = h("li", {}, `<button class="act ghost">✕</button>${i === 0 ? "fit" : "check"}: ${px.toFixed(1)} px = <b>${p.distance_m} m</b>`);
    $(".act", li).onclick = () => { S.pairs.splice(i, 1); renderPairs(); render(); };
    ul.appendChild(li);
  });
  const ev = S.fd && S.fd.transform.scale_evidence;
  if (ev && ev.length) for (const e of ev) if (e.residual_m !== undefined) ul.appendChild(h("li", {}, `last check residual: <b>${e.residual_m} m</b>`));
  $("#applyScale").disabled = !S.pairs.length || !S.fd;
}
function issueRefXY(ref) {
  if (!ref || !S.fd) return null;
  const n = S.fd.graph.nodes.find((x) => x.id === ref); if (n) return [n.x, n.y];
  const d = S.fd.doors.find((x) => x.id === ref); if (d) return [(d.a[0] + d.b[0]) / 2, (d.a[1] + d.b[1]) / 2];
  const r = S.fd.rooms.find((x) => x.id === ref);
  if (r) { const xs = r.polygon.map((p) => p[0]), ys = r.polygon.map((p) => p[1]); return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2]; }
  return null;
}
function renderChecks() {
  const ul = $("#issueList"); ul.innerHTML = "";
  if (!S.fd) { $("#checkSummary").innerHTML = ""; return; }
  const v = S.fd.validation;
  $("#checkSummary").innerHTML = kv([["Export", v.passed ? '<span class="badge ok">allowed</span>' : '<span class="badge err">blocked by errors</span>'],
    ["Errors", v.errors.length], ["Warnings", v.warnings.length]]);
  const all = v.errors.map((x) => ({ ...x, err: true })).concat(v.warnings);
  if (!all.length) ul.appendChild(h("li", { className: "empty" }, "No issues."));
  for (const it of all) {
    const li = h("li", { className: "issue" + (it.err ? " err" : "") }, `<code>${esc(it.code)}</code>${it.ref ? ` · ${esc(it.ref)}` : ""}<br>${esc(it.message)}`);
    li.onclick = () => {
      const xy = issueRefXY(it.ref); if (!xy) return;
      const kind = S.fd.graph.nodes.some((n) => n.id === it.ref) ? "node" : S.fd.doors.some((d) => d.id === it.ref) ? "door" : S.fd.rooms.some((r) => r.id === it.ref) ? "room" : null;
      if (kind) S.sel = { kind, id: it.ref };
      centerOn(toPx(xy[0]), toPx(xy[1])); render(); renderProps();
    };
    ul.appendChild(li);
  }
}
async function renderLinks() {
  const ul = $("#linkList"); if (!S.pid) return; ul.innerHTML = "";
  let L; try { L = await api(`${P()}/links`); } catch (_) { return; }
  S.links = L;
  const key = (e) => `${e.floor_id}:${e.node_id}`;
  if (!L.links.length) ul.appendChild(h("li", { className: "empty" }, "No links (needs 2+ floors with stairs or lifts)."));
  L.links.forEach((k) => {
    const li = h("li", {}, `${esc(k.type)} · ${esc(key(k.from))} ⇄ ${esc(key(k.to))} <span class="badge ${k.provenance.source === "manual" ? "edit" : ""}">${esc(k.provenance.source)}</span>`);
    if (k.provenance.source === "manual") {
      const b = h("button", { className: "act danger" }, "×");
      b.onclick = async () => {
        const rest = (L.manual || []).filter((m) => !(key(m.from) === key(k.from) && key(m.to) === key(k.to)));
        await api(`${P()}/links`, { method: "PUT", json: { manual: rest } }); renderLinks();
      };
      li.prepend(b);
    }
    ul.appendChild(li);
  });
  L.warnings.forEach((w) => ul.appendChild(h("li", { className: "issue" }, `<code>${esc(w.code)}</code><br>${esc(w.message)}`)));
  const opts = Object.entries(L.nodes).flatMap(([f, ns]) => ns.map((n) => `<option value="${esc(f)}:${esc(n.id)}:${esc(n.type)}">${esc(f)} · ${esc(n.id)} (${esc(n.type)})</option>`)).join("");
  $("#linkA").innerHTML = opts; $("#linkB").innerHTML = opts;
}
function selected() {
  if (!S.sel || !S.fd) return null;
  const pool = { node: S.fd.graph.nodes, edge: S.fd.graph.edges, door: S.fd.doors, room: S.fd.rooms, poi: S.fd.pois }[S.sel.kind];
  return pool ? pool.find((x) => x.id === S.sel.id) : null;
}
function renderProps() {
  const box = $("#props"); const x = selected();
  if (!x) { box.innerHTML = '<p class="note">Select something on the map to edit it. Tools: S select, N node, E edge, D door, P place, V not walkable, W walkable.</p>'; return; }
  const k = S.sel.kind;
  let html = `<div class="label">${k} <code>${esc(x.id)}</code> <span class="badge">${esc(x.provenance ? x.provenance.source : "")}</span></div>`;
  if (k === "room") {
    html += `<label class="fld">Label <input data-f="label" value="${esc(x.label)}"></label>
      <label class="fld">Name <input data-f="name" value="${esc(x.name)}"></label>
      <label class="fld">Category <select data-f="category">${["", "room", "office", "classroom", "lab", "toilet", "stairs_or_lift", "other"].map((c) => `<option ${x.category === c || (!x.category && !c) ? "selected" : ""} value="${c}">${c || "(none)"}</option>`).join("")}</select></label>
      <button id="roomVoid" class="ghost wide">Make this room not walkable (void / shaft)</button>
      <button id="roomPoi" class="ghost wide">Create a place for this room</button>`;
  } else if (k === "poi") {
    html += `<label class="fld">Name <input data-f="name" value="${esc(x.name)}"></label>
      <label class="fld">Label <input data-f="label" value="${esc(x.label)}"></label>
      <label class="fld">Category <input data-f="category" value="${esc(x.category)}"></label>
      <label class="chk"><input type="checkbox" data-f="needs_review" ${x.needs_review ? "checked" : ""}> needs review</label>`;
  } else if (k === "node") {
    html += `<label class="fld">Kind <select data-f="kind">${["corridor", "junction", "door", "transition"].map((c) => `<option ${x.kind === c ? "selected" : ""}>${c}</option>`).join("")}</select></label>
      <label class="fld">Transition <select data-f="transition">${["", "stairs", "lift", "escalator"].map((c) => `<option value="${c}" ${(x.transition || "") === c ? "selected" : ""}>${c || "(none)"}</option>`).join("")}</select></label>
      <p class="note">x ${x.x.toFixed(2)} m, y ${x.y.toFixed(2)} m · drag to move</p>`;
  } else if (k === "edge") {
    html += `<p class="note">${esc(x.from)} → ${esc(x.to)} · ${x.length_m} m</p>
      <label class="fld">Type <select data-f="type">${["corridor", "door", "stairs", "lift", "escalator"].map((c) => `<option ${x.type === c ? "selected" : ""}>${c}</option>`).join("")}</select></label>
      <label class="chk"><input type="checkbox" data-f="accessible" ${x.accessible ? "checked" : ""}> step-free (accessible)</label>`;
  } else if (k === "door") {
    html += `<p class="note">width ${dist(x.a, x.b).toFixed(2)} m · room ${esc(x.room_id || "–")}</p>`;
  }
  box.innerHTML = html;
  for (const inp of $$("[data-f]", box)) {
    inp.onchange = () => {
      pushUndo();
      const f = inp.dataset.f;
      let v = inp.type === "checkbox" ? inp.checked : inp.value;
      if (v === "" && f !== "name") v = null;
      if (f === "transition" && !v) delete x.transition; else x[f] = v;
      touch(x); commit();
    };
  }
  if (k === "room") {
    $("#roomVoid").onclick = () => walkableOp(x.polygon, "remove");
    $("#roomPoi").onclick = () => {
      const c = issueRefXY(x.id);
      const near = nearestNode(c);
      if (!near) { alert("No graph node found; add a node inside or next to the room first."); return; }
      pushUndo();
      const p = { id: uid("p", S.fd.pois), name: x.name || x.label || x.id, label: x.label, node_id: near.id, room_id: x.id,
        category: x.category, needs_review: true, provenance: { source: "manual" } };
      S.fd.pois.push(p); S.sel = { kind: "poi", id: p.id }; commit();
    };
  }
}

// ---------------------------------------------------------------- overlay rendering
function render() {
  const svg = $("#ov"); svg.innerHTML = "";
  const L = S.layers; const fd = S.fd; const k = S.view.k;
  $("#maskCanvas").style.display = L.masks || S.tab === "input" ? "" : "none";
  $("#eraseCanvas").style.display = S.tab === "input" ? "" : "none";
  if (fd) {
    const s = sc(); const P2 = (p) => `${(p[0] / s).toFixed(1)},${(p[1] / s).toFixed(1)}`;
    if (L.walkable) {
      const d = fd.walkable.coordinates.map((poly) => poly.map((ring) => "M" + ring.map(P2).join("L") + "Z").join("")).join("");
      el("path", { d, class: "walk", "fill-rule": "evenodd" }, svg);
    }
    if (L.rooms) for (const r of fd.rooms) {
      const g = el("g", {}, svg);
      el("polygon", { points: r.polygon.map(P2).join(" "), class: `room ${r.provenance.source}${isSel("room", r.id) ? " sel" : ""}`, "data-kind": "room", "data-id": r.id }, g);
      const c = issueRefXY(r.id); const t = el("text", { x: toPx(c[0]), y: toPx(c[1]), class: "roomlbl", "text-anchor": "middle", "font-size": 13 / k }, g);
      t.textContent = r.label || r.name || "";
    }
    if (L.walls) for (const w of fd.walls) el("line", { x1: toPx(w.a[0]), y1: toPx(w.a[1]), x2: toPx(w.b[0]), y2: toPx(w.b[1]), class: "wall" }, svg);
    if (L.doors) for (const d of fd.doors) el("line", { x1: toPx(d.a[0]), y1: toPx(d.a[1]), x2: toPx(d.b[0]), y2: toPx(d.b[1]), class: "door" + (isSel("door", d.id) ? " sel" : ""), "data-kind": "door", "data-id": d.id }, svg);
    const nodes = Object.fromEntries(fd.graph.nodes.map((n) => [n.id, n]));
    if (L.graph) {
      for (const e of fd.graph.edges) {
        const a = nodes[e.from], b = nodes[e.to]; if (!a || !b) continue;
        const at = { x1: toPx(a.x), y1: toPx(a.y), x2: toPx(b.x), y2: toPx(b.y) };
        el("line", { ...at, class: "edge" + (isSel("edge", e.id) ? " sel" : "") }, svg);
        el("line", { ...at, class: "edge hit", "data-kind": "edge", "data-id": e.id }, svg);
      }
      for (const n of fd.graph.nodes) el("circle", { cx: toPx(n.x), cy: toPx(n.y), r: (isSel("node", n.id) ? 7 : 5) / k,
        class: `node ${n.kind} ${n.provenance ? n.provenance.source : ""}${isSel("node", n.id) ? " sel" : ""}`, "data-kind": "node", "data-id": n.id }, svg);
    }
    if (L.pois) for (const p of fd.pois) {
      const n = nodes[p.node_id]; if (!n) continue;
      const t = el("text", { x: toPx(n.x) + 7 / k, y: toPx(n.y) - 7 / k, class: "poilbl", "font-size": 12 / k, "data-kind": "poi", "data-id": p.id }, svg);
      t.textContent = (isSel("poi", p.id) ? "▶ " : "") + (p.label || p.name || p.id);
      t.style.pointerEvents = "auto";
    }
  }
  // drafts (polygons, door, crop, measurements)
  if (S.draft.length && ["void", "walk", "door", "crop"].includes(S.tool)) {
    if (S.tool === "crop" && S.draft.length === 2) {
      const [a, b] = S.draft; el("rect", { x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), width: Math.abs(a[0] - b[0]), height: Math.abs(a[1] - b[1]), class: "crop" }, svg);
    } else el("polyline", { points: S.draft.map((p) => p.join(",")).join(" "), class: "draft" }, svg);
  }
  const meas = S.pairs.map((p) => [p.p1_px, p.p2_px]); if (S.tool === "measure" && S.draft.length) meas.push(S.draft.length === 1 ? [S.draft[0], S.draft[0]] : S.draft);
  for (const [a, b] of meas) { el("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: "meas" }, svg); for (const p of [a, b]) el("circle", { cx: p[0], cy: p[1], r: 4 / k, class: "measpt" }, svg); }
}
const isSel = (kind, id) => S.sel && S.sel.kind === kind && S.sel.id === id;

// ---------------------------------------------------------------- view (pan/zoom)
function applyView() { $("#stage").style.transform = `translate(${S.view.x}px, ${S.view.y}px) scale(${S.view.k})`; }
function fit() {
  const vp = $("#viewport").getBoundingClientRect();
  if (!S.w) return;
  const k = Math.min((vp.width - 40) / S.w, (vp.height - 40) / S.h);
  S.view = { k, x: (vp.width - S.w * k) / 2, y: (vp.height - S.h * k) / 2 };
  applyView(); render();
}
function zoomAt(cx, cy, f) {
  const v = S.view; const k = Math.min(Math.max(v.k * f, 0.05), 20);
  v.x = cx - (cx - v.x) * (k / v.k); v.y = cy - (cy - v.y) * (k / v.k); v.k = k; applyView(); render();
}
function centerOn(px, py) { const vp = $("#viewport").getBoundingClientRect(); S.view.x = vp.width / 2 - px * S.view.k; S.view.y = vp.height / 2 - py * S.view.k; applyView(); }
function toImg(ev) { const r = $("#viewport").getBoundingClientRect(); return [(ev.clientX - r.left - S.view.x) / S.view.k, (ev.clientY - r.top - S.view.y) / S.view.k]; }

// ---------------------------------------------------------------- editing
function pushUndo() { if (S.fd) { S.undo.push(JSON.stringify(S.fd)); if (S.undo.length > 60) S.undo.shift(); } }
function touch(x) { if (x.provenance && x.provenance.source === "auto") x.provenance.source = "corrected"; }
function commit() {
  S.fd._edited = true; render(); renderProps();
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(saveFloor, 500);
}
async function saveFloor() {
  if (!S.fd) return;
  try {
    status("Saving and validating…", true);
    const r = await api(`${F()}/floor`, { method: "PUT", json: S.fd });
    S.fd = r.floor; S.rec = r.record;
    if (S.sel && !selected()) S.sel = null;
    renderPanels(); render(); S.project = await api(P()); renderFloors();
    status(S.fd.validation.passed ? "Saved. Floor is valid." : `Saved. ${S.fd.validation.errors.length} error(s) block export (see Check).`);
  } catch (e) { status("Save failed: " + e.message); }
}
function nearestNode(m, maxM = Infinity) {
  let best = null, bd = maxM;
  for (const n of S.fd.graph.nodes) { const d = Math.hypot(n.x - m[0], n.y - m[1]); if (d < bd) { bd = d; best = n; } }
  return best;
}
function addNode(m, kind = "junction", extra = {}) {
  const n = { id: uid("m", S.fd.graph.nodes), x: +m[0].toFixed(3), y: +m[1].toFixed(3), kind, door_id: null, provenance: { source: "manual" }, ...extra };
  S.fd.graph.nodes.push(n); return n;
}
function addEdge(a, b) {
  if (a.id === b.id || S.fd.graph.edges.some((e) => (e.from === a.id && e.to === b.id) || (e.from === b.id && e.to === a.id))) return null;
  const e = { id: uid("me", S.fd.graph.edges), from: a.id, to: b.id, length_m: +Math.hypot(a.x - b.x, a.y - b.y).toFixed(3), type: "corridor",
    bidirectional: true, accessible: null, provenance: { source: "manual" } };
  S.fd.graph.edges.push(e); return e;
}
function deleteSelected() {
  const x = selected(); if (!x) return;
  pushUndo();
  const k = S.sel.kind; const fd = S.fd;
  if (k === "node") { fd.graph.nodes = fd.graph.nodes.filter((n) => n.id !== x.id); fd.graph.edges = fd.graph.edges.filter((e) => e.from !== x.id && e.to !== x.id); }
  if (k === "edge") fd.graph.edges = fd.graph.edges.filter((e) => e.id !== x.id);
  if (k === "door") fd.doors = fd.doors.filter((d) => d.id !== x.id);
  if (k === "room") fd.rooms = fd.rooms.filter((r) => r.id !== x.id);
  if (k === "poi") fd.pois = fd.pois.filter((p) => p.id !== x.id);
  S.sel = null; commit();
}
async function walkableOp(polyM, op) {
  if (S.saveTimer) { clearTimeout(S.saveTimer); await saveFloor(); }
  pushUndo();
  const r = await task(op === "remove" ? "Marking area not walkable" : "Adding walkable area", () => api(`${F()}/walkable`, { method: "POST", json: { polygon: polyM, op } }));
  if (r) { S.fd = r.floor; S.rec = r.record; S.sel = null; renderPanels(); render(); }
}
function finishDraft() {
  const s = sc();
  if ((S.tool === "void" || S.tool === "walk") && S.draft.length >= 3) walkableOp(S.draft.map((p) => [p[0] * s, p[1] * s]), S.tool === "void" ? "remove" : "add");
  S.draft = []; render();
}

// ---------------------------------------------------------------- painting
function paintAt(p) {
  const r = Number($("#brush").value);
  if (S.tool === "erase") {
    const ctx = $("#eraseCanvas").getContext("2d"); ctx.fillStyle = "rgb(255,40,40)";
    ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 7); ctx.fill(); S.eraseDirty = true;
  } else if (S.tool === "paint") {
    const ctx = $("#maskCanvas").getContext("2d");
    ctx.fillStyle = ["rgb(255,255,255)", "rgb(40,40,40)", "rgb(120,190,240)"][S.paintCls];
    ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 7); ctx.fill(); S.maskDirty = true;
  }
}
function paintLine(a, b) { const n = Math.max(1, Math.ceil(dist(a, b) / 2)); for (let i = 0; i <= n; i++) paintAt([a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n]); }
async function saveErase() {
  if (!S.eraseDirty) return;
  await api(`${F()}/erase`, { method: "PUT", json: { png: $("#eraseCanvas").toDataURL("image/png") } });
  S.eraseDirty = false;
}

// ---------------------------------------------------------------- mouse
let drag = null;
const vp = $("#viewport");
vp.addEventListener("wheel", (e) => { e.preventDefault(); const r = vp.getBoundingClientRect(); zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.15 : 1 / 1.15); }, { passive: false });
vp.addEventListener("contextmenu", (e) => e.preventDefault());
vp.addEventListener("mousedown", (e) => {
  if (!S.rec) return;
  const p = toImg(e); const m = [p[0] * sc(), p[1] * sc()];
  const t = e.target.closest("[data-kind]"); const hit = t ? { kind: t.dataset.kind, id: t.dataset.id } : null;
  if (e.button === 1 || e.button === 2 || (e.button === 0 && (!S.tool || e.altKey || (S.tool === "select" && !hit)))) {
    if (S.tool === "select" && !hit && e.button === 0) { S.sel = null; render(); renderProps(); }
    drag = { pan: true, x: e.clientX, y: e.clientY, vx: S.view.x, vy: S.view.y }; return;
  }
  if (S.tool === "erase" || S.tool === "paint") { drag = { paint: true, last: p }; paintAt(p); return; }
  if (!S.fd && !["crop", "measure"].includes(S.tool)) { status("Run the floor first."); return; }
  switch (S.tool) {
    case "select":
      S.sel = hit; render(); renderProps();
      if (hit && hit.kind === "node") { pushUndo(); drag = { node: selected(), moved: false }; }
      break;
    case "node": {
      pushUndo();
      const prev = S.sel && S.sel.kind === "node" ? selected() : null;
      const n = hit && hit.kind === "node" ? S.fd.graph.nodes.find((x) => x.id === hit.id) : addNode(m);
      if (prev && prev !== n) addEdge(prev, n);
      S.sel = { kind: "node", id: n.id }; commit(); break;
    }
    case "edge": {
      if (!hit || hit.kind !== "node") { status("Click a node, then another node."); break; }
      const n = S.fd.graph.nodes.find((x) => x.id === hit.id);
      if (S.sel && S.sel.kind === "node" && S.sel.id !== n.id) { pushUndo(); addEdge(selected(), n); S.sel = { kind: "node", id: n.id }; commit(); }
      else { S.sel = { kind: "node", id: n.id }; render(); renderProps(); status("Now click the node to connect to."); }
      break;
    }
    case "door":
      S.draft.push(p);
      if (S.draft.length === 2) {
        pushUndo(); const s = sc();
        const a = [S.draft[0][0] * s, S.draft[0][1] * s], b = [S.draft[1][0] * s, S.draft[1][1] * s];
        const d = { id: uid("md", S.fd.doors), a: a.map((v) => +v.toFixed(3)), b: b.map((v) => +v.toFixed(3)), room_id: null, provenance: { source: "manual", confidence: 1 } };
        S.fd.doors.push(d);
        const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        const near = nearestNode(mid, 4);
        const dn = addNode(mid, "door", { door_id: d.id });
        if (near) addEdge(dn, near);
        S.draft = []; S.sel = { kind: "node", id: dn.id }; commit();
        status(near ? `Door added and linked to ${near.id}. Use Add edge to link the room side.` : "Door added. Link its node with Add edge.");
      } else render();
      break;
    case "poi": {
      if (!hit || hit.kind !== "node") { status("Click the graph node where the place should be."); break; }
      const name = prompt("Name of the place (e.g. 'CS Lab 3', 'Dean office'):"); if (!name) break;
      pushUndo();
      const pp = { id: uid("p", S.fd.pois), name, label: null, node_id: hit.id, room_id: null, category: null, needs_review: false, provenance: { source: "manual" } };
      S.fd.pois.push(pp); S.sel = { kind: "poi", id: pp.id }; commit(); break;
    }
    case "void": case "walk":
      if (S.draft.length >= 3 && dist(p, S.draft[0]) < 10 / S.view.k) { finishDraft(); break; }
      S.draft.push(p); render(); status("Click points; click the first point (or press Enter) to finish, Esc to cancel."); break;
    case "crop": S.draft = [p, p]; drag = { crop: true }; break;
    case "measure":
      S.draft.push(p);
      if (S.draft.length === 2) {
        const dm = prompt(`Real distance between the two points, in metres (${dist(S.draft[0], S.draft[1]).toFixed(1)} px):`);
        if (dm && Number(dm) > 0) S.pairs.push({ p1_px: S.draft[0], p2_px: S.draft[1], distance_m: Number(dm) });
        S.draft = []; renderPairs();
      }
      render(); break;
  }
});
window.addEventListener("mousemove", (e) => {
  if (S.rec) { const p = toImg(e); $("#coords").textContent = S.fd ? `${(p[0] * sc()).toFixed(2)} m, ${(p[1] * sc()).toFixed(2)} m · ${p[0].toFixed(0)}, ${p[1].toFixed(0)} px` : `${p[0].toFixed(0)}, ${p[1].toFixed(0)} px`; }
  if (!drag) return;
  if (drag.pan) { S.view.x = drag.vx + e.clientX - drag.x; S.view.y = drag.vy + e.clientY - drag.y; applyView(); return; }
  const p = toImg(e);
  if (drag.paint) { paintLine(drag.last, p); drag.last = p; return; }
  if (drag.node) { drag.node.x = +(p[0] * sc()).toFixed(3); drag.node.y = +(p[1] * sc()).toFixed(3); drag.moved = true; touch(drag.node); render(); return; }
  if (drag.crop) { S.draft[1] = p; render(); }
});
window.addEventListener("mouseup", () => {
  if (!drag) return;
  if (drag.node) { if (drag.moved) commit(); else S.undo.pop(); }
  if (drag.crop && S.draft.length === 2) {
    const [a, b] = S.draft;
    if (Math.abs(a[0] - b[0]) > 20 && Math.abs(a[1] - b[1]) > 20 && confirm("Crop the plan to this rectangle? The floor must be run again afterwards.")) {
      const crop = [a[0], a[1], b[0], b[1]].map(Math.round);
      const cur = S.rec.crop; // crop is relative to the loaded+rotated image: add the previous offset
      if (cur) { crop[0] += Math.min(cur[0], cur[2]); crop[2] += Math.min(cur[0], cur[2]); crop[1] += Math.min(cur[1], cur[3]); crop[3] += Math.min(cur[1], cur[3]); }
      prepareFloor({ crop });
    }
    S.draft = []; render();
  }
  drag = null;
});
window.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea")) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); return; }
  if (e.key === "Delete" || e.key === "Backspace") { deleteSelected(); return; }
  if (e.key === "Escape") { S.draft = []; render(); return; }
  if (e.key === "Enter") { finishDraft(); return; }
  const map = { s: "select", n: "node", e: "edge", d: "door", p: "poi", v: "void", w: "walk" };
  if (S.tab === "map" && map[e.key.toLowerCase()]) setTool(map[e.key.toLowerCase()]);
});
function undo() { const last = S.undo.pop(); if (!last) { status("Nothing to undo."); return; } S.fd = JSON.parse(last); S.sel = null; commit(); }

// ---------------------------------------------------------------- tools & tabs
function setTool(tool, btn) {
  S.tool = S.tool === tool && !btn?.dataset.cls ? null : tool; S.draft = [];
  if (btn && btn.dataset.cls !== undefined) { S.paintCls = Number(btn.dataset.cls); S.tool = "paint"; }
  $$("[data-tool]").forEach((b) => b.classList.toggle("on", b.dataset.tool === S.tool && (S.tool !== "paint" || Number(b.dataset.cls) === S.paintCls)));
  vp.classList.toggle("tool", !!S.tool && S.tool !== "select");
  const hints = { crop: "Drag a rectangle around the floor to keep.", erase: "Paint over legends, title blocks or marks to remove them from the input.",
    paint: "Paint the masks; then press Re-run from edited masks.", node: "Click to add a node; it connects to the selected node (chains).",
    edge: "Click a node, then another node.", door: "Click the two ends of the door opening.", poi: "Click a graph node to name a place there.",
    void: "Draw a polygon around an area that cannot be walked (void, shaft, blocked).", walk: "Draw a polygon of walkable area to add.",
    measure: "Click two points with a known real distance.", select: "Click to select; drag nodes to move; Delete removes." };
  $("#hint").hidden = !S.tool; $("#hint").textContent = hints[S.tool] || "";
  if (S.tool === "paint" && !S.maskLoaded) loadMasks();
  render();
}
$$("[data-tool]").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool, b)));
$$("#tabs button").forEach((b) => b.addEventListener("click", () => {
  S.tab = b.dataset.tab;
  $$("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
  $$(".tab").forEach((t) => (t.hidden = t.dataset.tab !== S.tab));
  if (S.tab === "input" && S.fd && !S.maskLoaded) loadMasks();
  setTool(S.tab === "map" ? "select" : null);
}));
$$("#layers input").forEach((c) => { S.layers[c.dataset.layer] = c.checked; c.addEventListener("change", () => { S.layers[c.dataset.layer] = c.checked; if (c.dataset.layer === "masks" && c.checked && !S.maskLoaded) loadMasks(); render(); }); });
$("#brush").addEventListener("input", (e) => ($("#brushV").textContent = e.target.value));

// ---------------------------------------------------------------- actions
$("#newProject").onclick = async () => {
  const name = prompt("Project (venue) name, e.g. 'FAST Islamabad':"); if (!name) return;
  const p = await task("Creating project", () => api("/api/projects", { method: "POST", json: { name } }));
  if (p) await loadProjects(p.id);
};
$("#projectSel").onchange = (e) => e.target.value && openProject(e.target.value);
$("#uploadBtn").onclick = () => $("#fileInput").click();
$("#fileInput").onchange = async (e) => {
  const file = e.target.files[0]; e.target.value = ""; if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  const info = await task("Uploading " + file.name, () => api(`${P()}/files`, { method: "POST", form: fd }));
  if (!info) return;
  S.project = await api(P()); renderFiles(); openAddFloor(file.name);
};
$("#runBtn").onclick = async () => {
  await saveErase();
  const r = await task("Running automatic mapping", () => api(`${F()}/run`, { method: "POST", json: { segmenter: $("#segSel").value } }));
  if (!r) return;
  S.fd = r.floor; S.rec = r.record; S.sel = null; S.undo = []; S.maskLoaded = false;
  if (S.layers.masks || S.tab === "input") loadMasks();
  S.project = await api(P()); renderFloors(); renderPanels(); render();
};
$("#rerunMasks").onclick = async () => {
  await saveErase();
  if (S.maskDirty) await api(`${F()}/masks`, { method: "PUT", json: { png: $("#maskCanvas").toDataURL("image/png") } });
  const r = await task("Re-running from edited masks", () => api(`${F()}/run`, { method: "POST", json: { from_masks: true } }));
  if (!r) return;
  S.maskDirty = false; S.fd = r.floor; S.rec = r.record; S.sel = null; S.undo = [];
  S.project = await api(P()); renderFloors(); renderPanels(); render();
};
$("#revertBtn").onclick = async () => {
  if (!confirm("Discard all manual edits on the map and go back to the last automatic result?")) return;
  const r = await task("Reverting", () => api(`${F()}/revert`, { method: "POST" }));
  if (r) { S.fd = r.floor; S.rec = r.record; S.undo = []; S.sel = null; renderPanels(); render(); }
};
$("#clearErase").onclick = () => { const c = $("#eraseCanvas"); c.getContext("2d").clearRect(0, 0, c.width, c.height); S.eraseDirty = true; };
$$("[data-rot]").forEach((b) => (b.onclick = () => {
  if (!confirm("Rotate the plan? The floor must be run again afterwards.")) return;
  prepareFloor({ rotate: ((S.rec.rotate || 0) + Number(b.dataset.rot)) % 360, crop: null });
}));
async function prepareFloor(body) {
  const rec = await task("Reloading the plan", () => api(`${F()}/prepare`, { method: "POST", json: { crop: S.rec.crop, ...body } }));
  if (rec) await openFloor(S.fid);
}
$("#applyScale").onclick = async () => {
  if (S.saveTimer) { clearTimeout(S.saveTimer); await saveFloor(); }
  const r = await task("Applying scale", () => api(`${F()}/scale`, { method: "POST", json: { pairs: S.pairs } }));
  if (r && r.floor) { S.fd = r.floor; S.rec = r.record; S.pairs = []; renderPanels(); render(); }
};
$("#undoBtn").onclick = undo;
$("#delBtn").onclick = deleteSelected;
$("#zoomIn").onclick = () => { const r = vp.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, 1.25); };
$("#zoomOut").onclick = () => { const r = vp.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, 0.8); };
$("#zoomFit").onclick = fit;
$("#exportBtn").onclick = (e) => { e.stopPropagation(); $("#exportMenu").hidden = !$("#exportMenu").hidden; };
document.addEventListener("click", (e) => { if (!e.target.closest(".menu")) $("#exportMenu").hidden = true; });
$$("#exportMenu a").forEach((a) => (a.onclick = async () => {
  if (S.saveTimer) { clearTimeout(S.saveTimer); await saveFloor(); }
  const inc = $("#includeFailed").checked ? "?include_failed=true" : "";
  const r = await task("Exporting " + a.dataset.fmt, () => api(`${P()}/export/${a.dataset.fmt}${inc}`));
  if (!r) return;
  const blob = await r.blob();
  const name = (r.headers.get("content-disposition") || "").match(/filename="([^"]+)"/)?.[1] || "export";
  const url = URL.createObjectURL(blob); const link = h("a", { href: url, download: name }); document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  $("#exportMenu").hidden = true; status(`Exported ${name} (a copy is also kept in the project's exports folder).`);
}));
window.addEventListener("resize", () => S.w && applyView());

// ---------------------------------------------------------------- start
(async () => {
  try { await loadInfo(); await loadProjects(); if (!S.pid) clearFloor(); if (S.info.ocr && S.info.ocr.available) status(`TURN Studio ${S.info.version} · projects in ${S.info.root}`); }
  catch (e) { status("Could not reach the Studio server: " + e.message); }
})();
