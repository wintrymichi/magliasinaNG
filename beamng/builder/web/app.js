/* Switzerland Builder: the page. Plain JavaScript and Leaflet; everything it does goes through the local API. */
"use strict";

const TOKEN = document.querySelector('meta[name="builder-token"]').content;
const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const o = { headers: { "X-Builder-Token": TOKEN } };
  if (opts.body !== undefined) {
    o.method = "POST";
    o.headers["Content-Type"] = "application/json";
    o.body = JSON.stringify(opts.body);
  }
  const r = await fetch(path, o);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ------------------------------------------------------------------ the map */
const CH = L.latLngBounds([45.78, 5.9], [47.86, 10.55]);
const map = L.map("map", { zoomControl: true, minZoom: 7, maxBounds: CH.pad(0.35), zoomSnap: 0.5 }).fitBounds(CH);
const wmts = (layer, ext = "jpeg", maxNative = 18) => L.tileLayer(
  `https://wmts.geo.admin.ch/1.0.0/${layer}/default/current/3857/{z}/{x}/{y}.${ext}`,
  { maxZoom: 19, maxNativeZoom: maxNative, attribution: '© <a href="https://www.swisstopo.admin.ch" target="_blank" rel="noopener">swisstopo</a>' });
const base = {
  "Map": wmts("ch.swisstopo.pixelkarte-farbe"),
  "Aerial (SWISSIMAGE)": wmts("ch.swisstopo.swissimage", "jpeg", 19),
  "Grey map": wmts("ch.swisstopo.pixelkarte-grau"),
};
base["Map"].addTo(map);
const cantons = L.layerGroup().addTo(map);
const buildsLayer = L.layerGroup().addTo(map);
L.control.layers(base, { "Cantons": cantons, "Builds": buildsLayer }, { position: "topleft" }).addTo(map);
L.control.scale({ imperial: false }).addTo(map);
api("/api/regions").then((g) => {
  L.geoJSON(g, { style: { color: "#d52b1e", weight: 1, opacity: 0.55, fill: false, dashArray: "2 3" }, interactive: false })
    .addTo(cantons);
}).catch(() => {});

/* ------------------------------------------------------------------ the area */
let sel = null;             // L.LatLngBounds
let rect = null, terrain = null, handles = [];
let lastCheck = null;
let checkTimer = null;
let drawing = false, drawStart = null;

function setSelection(b, fly = false) {
  sel = b;
  if (!rect) {
    rect = L.polygon([], { color: "#d52b1e", weight: 2, fillOpacity: 0.12 }).addTo(map);
    terrain = L.polygon([], { color: "#1d2126", weight: 1.5, dashArray: "6 5", fill: false, interactive: false }).addTo(map);
  }
  rect.setLatLngs([b.getSouthWest(), b.getSouthEast(), b.getNorthEast(), b.getNorthWest()]);
  placeHandles();
  if (fly) map.fitBounds(b.pad(0.6));
  clearTimeout(checkTimer);
  checkTimer = setTimeout(runCheck, 250);
}

function placeHandles() {
  handles.forEach((h) => map.removeLayer(h));
  handles = [];
  if (!sel) return;
  const corners = [
    ["sw", sel.getSouthWest()], ["se", sel.getSouthEast()], ["ne", sel.getNorthEast()], ["nw", sel.getNorthWest()],
  ];
  for (const [k, ll] of corners) {
    const m = L.marker(ll, { draggable: true, icon: L.divIcon({ className: "handle" }), keyboard: false, title: "Drag the corner" });
    m.on("drag", (e) => {
      const p = e.target.getLatLng();
      let s = sel.getSouth(), w = sel.getWest(), n = sel.getNorth(), ea = sel.getEast();
      if (k.includes("s")) s = p.lat; else n = p.lat;
      if (k.includes("w")) w = p.lng; else ea = p.lng;
      sel = L.latLngBounds([Math.min(s, n), Math.min(w, ea)], [Math.max(s, n), Math.max(w, ea)]);
      rect.setLatLngs([sel.getSouthWest(), sel.getSouthEast(), sel.getNorthEast(), sel.getNorthWest()]);
    });
    m.on("dragend", () => setSelection(sel));
    handles.push(m.addTo(map));
  }
  const c = sel.getCenter();
  const mv = L.marker(c, { draggable: true, icon: L.divIcon({ className: "handle move" }), keyboard: false, title: "Drag to move the area" });
  let start = null;
  mv.on("dragstart", () => { start = { c: sel.getCenter(), b: sel }; });
  mv.on("drag", (e) => {
    const p = e.target.getLatLng();
    const dl = p.lat - start.c.lat, dn = p.lng - start.c.lng;
    sel = L.latLngBounds([start.b.getSouth() + dl, start.b.getWest() + dn], [start.b.getNorth() + dl, start.b.getEast() + dn]);
    rect.setLatLngs([sel.getSouthWest(), sel.getSouthEast(), sel.getNorthEast(), sel.getNorthWest()]);
  });
  mv.on("dragend", () => setSelection(sel));
  handles.push(mv.addTo(map));
}

function squareAt(center, km) {
  const dLat = (km / 2) / 111.32;
  const dLon = (km / 2) / (111.32 * Math.cos(center.lat * Math.PI / 180));
  return L.latLngBounds([center.lat - dLat, center.lng - dLon], [center.lat + dLat, center.lng + dLon]);
}

$("sq8").onclick = () => setSelection(squareAt(map.getCenter(), 8.0), true);
$("sq4").onclick = () => setSelection(squareAt(map.getCenter(), 4.0), true);

function setDrawing(on) {
  drawing = on;
  document.body.classList.toggle("drawing", on);
  $("draw").classList.toggle("active", on);
  $("draw").textContent = on ? "Drag on the map…" : "Draw a rectangle";
  if (on) map.dragging.disable(); else map.dragging.enable();
}
$("draw").onclick = () => setDrawing(!drawing);
map.on("mousedown", (e) => { if (drawing) { drawStart = e.latlng; } });
map.on("mousemove", (e) => {
  if (drawing && drawStart) {
    const b = L.latLngBounds(drawStart, e.latlng);
    if (!rect) setSelection(b); else { sel = b; rect.setLatLngs([b.getSouthWest(), b.getSouthEast(), b.getNorthEast(), b.getNorthWest()]); }
  }
});
map.on("mouseup", (e) => {
  if (drawing && drawStart) {
    const b = L.latLngBounds(drawStart, e.latlng);
    drawStart = null;
    setDrawing(false);
    if (Math.abs(b.getNorth() - b.getSouth()) > 0.001 && Math.abs(b.getEast() - b.getWest()) > 0.001) setSelection(b);
  }
});

async function runCheck() {
  if (!sel) return;
  const bbox = [sel.getSouth(), sel.getWest(), sel.getNorth(), sel.getEast()].map((v) => v.toFixed(6)).join(",");
  try {
    const c = await api("/api/check?bbox=" + bbox);
    lastCheck = c;
    if (c.terrain_wgs) terrain.setLatLngs(c.terrain_wgs);
    rect.setStyle({ color: c.ok ? "#d52b1e" : "#7a7a7a" });
    showInfo(c);
  } catch (e) {
    $("info").hidden = false;
    $("info").innerHTML = `<p class="msg err">${esc(e.message)}</p>`;
  }
  updateBuildButton();
}

function showInfo(c) {
  const i = $("info");
  i.hidden = false;
  const h = (v) => (v === undefined ? "–" : v);
  let html = "<dl>";
  if (c.side_x_m) html += `<dt>Size</dt><dd>${(c.side_x_m / 1000).toFixed(2)} × ${(c.side_y_m / 1000).toFixed(2)} km · ${h(c.km2)} km²</dd>`;
  if (c.canton_names) html += `<dt>Cantons</dt><dd>${esc(c.canton_names.join(", ") || "–")}</dd>`;
  if (c.osm_extracts) html += `<dt>Map data</dt><dd>${c.osm_extracts.length} OpenStreetMap extract${c.osm_extracts.length > 1 ? "s" : ""}</dd>`;
  if (c.estimate_hours !== undefined) html += `<dt>Build time</dt><dd>about ${c.estimate_hours} h <small>(on a 4-core PC)</small></dd>`;
  if (c.estimate_disk_gb !== undefined) html += `<dt>Disk</dt><dd>about ${c.estimate_disk_gb} GB</dd>`;
  html += "</dl>";
  for (const e of c.errors || []) html += `<p class="msg err">${esc(e)}</p>`;
  for (const w of c.warnings || []) html += `<p class="msg warn">${esc(w)}</p>`;
  i.innerHTML = html;
}

function updateBuildButton() {
  $("build").disabled = !(lastCheck && lastCheck.ok && sel);
}

$("build").onclick = async () => {
  if (!sel || !lastCheck || !lastCheck.ok) return;
  const name = $("name").value.trim() || guessName || "Swiss area";
  $("build").disabled = true;
  try {
    await api("/api/builds", { body: { name, bbox: [sel.getSouth(), sel.getWest(), sel.getNorth(), sel.getEast()] } });
    await refresh();
    document.getElementById("buildscard").scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    alert("The build could not start: " + e.message);
  } finally {
    updateBuildButton();
  }
};

/* ------------------------------------------------------------------ search */
let guessName = "";
let searchTimer = null;
$("q").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const q = $("q").value.trim();
    const ul = $("results");
    if (q.length < 2) { ul.hidden = true; return; }
    try {
      const res = await api("/api/search?q=" + encodeURIComponent(q));
      ul.innerHTML = res.map((r, k) => `<li data-k="${k}">${esc(r.label)}<small>${esc(r.origin || "")}</small></li>`).join("")
        || "<li><small>Nothing found</small></li>";
      ul.hidden = false;
      ul.querySelectorAll("li[data-k]").forEach((li) => {
        li.onclick = () => {
          const r = res[+li.dataset.k];
          ul.hidden = true;
          guessName = r.label.replace(/\s*\(.*\)\s*$/, "").split(/,\s*/)[0];
          if (!$("name").value) $("name").placeholder = guessName;
          map.setView([r.lat, r.lon], 13);
          if (!sel) setSelection(squareAt(L.latLng(r.lat, r.lon), 4.0));
        };
      });
    } catch (e) {
      ul.innerHTML = `<li><small>Search unavailable: ${esc(e.message)}</small></li>`;
      ul.hidden = false;
    }
  }, 300);
});
document.addEventListener("click", (e) => { if (!e.target.closest(".search")) $("results").hidden = true; });

/* ------------------------------------------------------------------ builds */
let state = null;
const outlines = {};
function fmtMin(m) {
  if (m == null) return "";
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

function renderBuilds() {
  const box = $("builds");
  const bs = state.builds;
  if (!bs.length) { box.innerHTML = '<p class="empty">No build yet.</p>'; return; }
  box.innerHTML = bs.map((b) => {
    const cur = b.steps.find((s) => s.status === "running") || b.steps.find((s) => s.status === "failed");
    const nDone = b.steps.filter((s) => s.status === "done" || s.status === "skipped").length;
    const pct = Math.round(100 * b.progress);
    const label = b.status === "done" ? `Done${b.zip_gb ? ` · ${b.zip_gb} GB zip` : ""}${b.installed ? " · in BeamNG's mods" : ""}`
      : cur ? `${esc(cur.label)} <span class="eta">· step ${nDone + 1} of ${b.steps.length}${b.status === "running" ? ` · about ${fmtMin(b.eta_minutes)} left` : ""}</span>`
      : `${nDone} of ${b.steps.length} steps`;
    const run = b.status === "running" || b.status === "queued";
    const acts = [
      `<button class="btn small" data-a="log">Log</button>`,
      run ? `<button class="btn small" data-a="cancel">Stop</button>` : "",
      !run && b.status !== "done" ? `<button class="btn small" data-a="start">${b.status === "new" ? "Start" : "Resume"}</button>` : "",
      b.zip_exists ? `<button class="btn small" data-a="install">Install in BeamNG</button>` : "",
      b.zip_exists ? `<button class="btn small ghost" data-a="openzip">Show zip</button>` : `<button class="btn small ghost" data-a="open">Folder</button>`,
      !run ? `<button class="btn small ghost danger" data-a="delete">Delete</button>` : "",
    ].join("");
    return `<div class="bcard ${b.status}" data-id="${esc(b.id)}">
      <div class="bhead"><strong>${esc(b.title)}</strong><span class="lvl">${esc(b.level)}</span>
        <span class="status ${b.status}">${esc(b.status)}</span></div>
      <div class="bar"><div style="width:${pct}%"></div></div>
      <div class="bstep">${label}</div>
      ${b.error ? `<div class="berr">${esc(b.error.split("\n")[0])}</div>` : ""}
      <div class="bactions">${acts}</div></div>`;
  }).join("");
  box.querySelectorAll(".bcard").forEach((el) => {
    const id = el.dataset.id;
    el.onclick = (e) => {
      const a = e.target.dataset.a;
      if (!a) { const b = state.builds.find((x) => x.id === id); if (b) map.fitBounds(L.latLngBounds([b.bbox[0], b.bbox[1]], [b.bbox[2], b.bbox[3]]).pad(0.5)); return; }
      e.stopPropagation();
      action(id, a);
    };
  });
  // outlines on the map
  for (const k of Object.keys(outlines)) { if (!bs.find((b) => b.id === k)) { buildsLayer.removeLayer(outlines[k]); delete outlines[k]; } }
  for (const b of bs) {
    const ll = (b.check && b.check.area_wgs) || [[b.bbox[0], b.bbox[1]], [b.bbox[0], b.bbox[3]], [b.bbox[2], b.bbox[3]], [b.bbox[2], b.bbox[1]]];
    const col = b.status === "done" ? "#1f7a3d" : b.status === "failed" ? "#b3261e" : "#1f5fbf";
    if (!outlines[b.id]) {
      outlines[b.id] = L.polygon(ll, { color: col, weight: 2, fillOpacity: 0.05 }).bindTooltip(esc(b.title), { className: "blabel", permanent: false });
      buildsLayer.addLayer(outlines[b.id]);
    } else outlines[b.id].setStyle({ color: col });
  }
}

async function action(id, a) {
  try {
    if (a === "log") return openLog(id);
    if (a === "delete" && !confirm("Delete this build and all its files (the downloads stay in the cache)?")) return;
    if (a === "openzip") return api(`/api/builds/${id}/open`, { body: { what: "zip" } });
    if (a === "install") {
      const r = await api(`/api/builds/${id}/install`, { body: {} });
      alert(r.ok ? `Installed: ${r.path}\n\nStart BeamNG.drive and pick the level in Freeroam.` : `Not installed: ${r.reason}${r.zip ? "\n\n" + r.zip : ""}`);
    } else {
      await api(`/api/builds/${id}/${a}`, { body: {} });
    }
    await refresh();
  } catch (e) { alert(e.message); }
}

function renderSystem() {
  const s = state.system;
  const chips = [];
  chips.push(`<span class="chip ${s.ram_gb >= 15 ? "ok" : "warn"}" title="Memory">${s.ram_gb} GB RAM${s.ram_gb < 15 ? " (16 GB advised)" : ""}</span>`);
  chips.push(`<span class="chip">${s.cpus} cores</span>`);
  chips.push(`<span class="chip ${s.free_gb >= 60 ? "ok" : s.free_gb >= 25 ? "warn" : "err"}" title="${esc(s.data_dir)}">${s.free_gb} GB free</span>`);
  chips.push(s.beamng_found ? `<span class="chip ok" title="${esc(s.beamng_user)}">BeamNG found</span>` : `<span class="chip warn" title="Set it in Settings">BeamNG not found</span>`);
  $("sysbar").innerHTML = chips.join("");
}

let settingsShown = false;
function renderSettings() {
  if (settingsShown) return;
  settingsShown = true;
  $("s_data").value = state.settings.data_dir || "";
  $("s_user").value = state.settings.beamng_user || "";
  $("s_workers").value = state.settings.workers || "auto";
  $("s_install").checked = state.settings.auto_install !== false;
  $("s_user_list").innerHTML = (state.system.beamng_candidates || []).map((p) => `<option value="${esc(p)}">`).join("");
}
$("s_save").onclick = async () => {
  try {
    state = await api("/api/settings", { body: { data_dir: $("s_data").value, beamng_user: $("s_user").value, workers: $("s_workers").value, auto_install: $("s_install").checked } });
    $("s_msg").textContent = "Saved.";
    renderSystem(); renderBuilds();
  } catch (e) { $("s_msg").textContent = e.message; }
};

async function refresh() {
  try {
    state = await api("/api/state");
    renderSystem(); renderSettings(); renderBuilds();
  } catch (e) {
    $("sysbar").innerHTML = `<span class="chip err">The app is not answering: ${esc(e.message)}</span>`;
  }
}
refresh();
setInterval(refresh, 3000);

/* ------------------------------------------------------------------ log */
let logId = null, logOff = 0, logTimer = null;
async function pullLog() {
  if (!logId) return;
  try {
    const r = await api(`/api/builds/${logId}/log?offset=${logOff}`);
    if (logOff === 0 && r.offset > r.text.length) $("logtext").textContent = "… (earlier lines left out)\n";
    logOff = r.offset;
    if (r.text) {
      const pre = $("logtext");
      pre.textContent += r.text;
      if (pre.textContent.length > 600000) pre.textContent = pre.textContent.slice(-400000);
      if ($("logfollow").checked) pre.scrollTop = pre.scrollHeight;
    }
  } catch (e) { /* keep trying */ }
}
function openLog(id) {
  const b = state.builds.find((x) => x.id === id);
  logId = id; logOff = Math.max(0, (b ? b.log_size : 0) - 200000);
  $("logtitle").textContent = `Log · ${b ? b.title : id}`;
  $("logtext").textContent = "";
  $("logbox").hidden = false;
  pullLog();
  clearInterval(logTimer);
  logTimer = setInterval(pullLog, 2000);
}
$("logclose").onclick = () => { $("logbox").hidden = true; logId = null; clearInterval(logTimer); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("logbox").hidden) $("logclose").onclick(); });

$("quit").onclick = async (e) => {
  e.preventDefault();
  if (!confirm("Quit the Switzerland Builder? A running build stops and can be resumed later.")) return;
  try { await api("/api/quit", { body: {} }); } catch (_) {}
  document.body.innerHTML = "<p style='padding:2em;font:16px system-ui'>The Switzerland Builder has stopped. Start it again with its launcher.</p>";
};
