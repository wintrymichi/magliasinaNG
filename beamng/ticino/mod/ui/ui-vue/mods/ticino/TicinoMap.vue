<template>
  <div class="tmap" ref="rootEl" tabindex="-1" @keydown.stop="onKey">
    <div class="view" ref="viewEl" @mousedown="onDown" @wheel.prevent="onWheel" @dblclick.prevent="zoomAt($event, 2)">
      <!-- the coarsest level under everything (no holes while the finer tiles load) -->
      <img v-for="t in underTiles" :key="'u' + t.key" class="tile" :src="t.src" draggable="false"
           :style="{ left: t.left + 'px', top: t.top + 'px', width: t.size + 1 + 'px', height: t.size + 1 + 'px' }" />
      <img v-for="t in tiles" :key="t.key" class="tile" :src="t.src" draggable="false"
           :style="{ left: t.left + 'px', top: t.top + 'px', width: t.size + 1 + 'px', height: t.size + 1 + 'px' }" />
      <!-- the places (spawn points by name): a click takes the car there -->
      <div v-for="p in shownPlaces" :key="p.name" class="place" :class="{ hot: hover === p.name }"
           :style="{ left: p.sx + 'px', top: p.sy + 'px' }"
           @mousedown.stop @click.stop="go(p)" @mouseenter="hover = p.name" @mouseleave="hover = null">
        <div class="dot"></div>
        <div class="label">{{ p.label }}</div>
      </div>
      <!-- the car -->
      <div v-if="carScreen" class="car" :style="{ left: carScreen.x + 'px', top: carScreen.y + 'px' }">
        <div class="arrow" :style="{ transform: 'rotate(' + carScreen.h + 'deg)' }"></div>
      </div>
    </div>

    <div class="top">
      <div class="title">Ticino</div>
      <input class="search" v-model="query" placeholder="Cerca un luogo..." @mousedown.stop
             @focus="typing(true)" @blur="typing(false)" @keydown.enter.stop.prevent="goFirst" />
      <button class="btn" @click="zoomBy(2)" title="Zoom in">+</button>
      <button class="btn" @click="zoomBy(0.5)" title="Zoom out">&minus;</button>
      <button class="btn wide" @click="centreCar" title="Centra sull'auto">Auto</button>
      <button class="btn wide" @click="fitAll" title="Tutto il Ticino">Ticino</button>
      <button class="btn" @click="close" title="Chiudi (M / Esc)">&times;</button>
    </div>
    <div v-if="query" class="results">
      <div v-for="p in found" :key="'f' + p.name" class="result" @mousedown.stop @click="go(p)"
           @mouseenter="hover = p.name" @mouseleave="hover = null">{{ p.label }}</div>
      <div v-if="!found.length" class="result none">Nessun luogo</div>
    </div>
    <div v-if="msg" class="msg">{{ msg }}</div>
    <div class="bottom">
      <span>Clic su un luogo: l'auto va li. Trascina per spostare, rotella per lo zoom, M o Esc per chiudere.</span>
      <span class="credits">{{ info && info.credits }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue"

const ROOT = "/levels/ticino/map/"
const rootEl = ref(null), viewEl = ref(null)
const w = ref(1280), h = ref(720)
const info = ref(null)
const view = ref({ x: 0, y: 0, mpp: 100 })     // the world point at the screen's centre, metres a screen pixel
const car = ref(null)
const query = ref("")
const hover = ref(null)
const msg = ref("")
let pollTimer = null, resizeObs = null, drag = null, centred = false

function engineLua(script, cb) {
  if (window.bngApi && window.bngApi.engineLua) window.bngApi.engineLua(script, cb)
}
function typing(on) { engineLua(`if setCEFTyping then setCEFTyping(${on ? "true" : "false"}) end`) }

// ---- the map's geometry
const levels = computed(() => (info.value ? info.value.levels : []))
const have = computed(() => levels.value.map(L => new Set(L.tiles)))
const maxMpp = computed(() => (levels.value.length ? levels.value[levels.value.length - 1].mpp * 2 : 1000))
const minMpp = computed(() => (info.value ? info.value.mpp0 / 3 : 1))

function toScreen(x, y) {
  const v = view.value
  return { x: w.value / 2 + (x - v.x) / v.mpp, y: h.value / 2 - (y - v.y) / v.mpp }
}
function toWorld(sx, sy) {
  const v = view.value
  return { x: v.x + (sx - w.value / 2) * v.mpp, y: v.y - (sy - h.value / 2) * v.mpp }
}

function tilesOf(z) {
  const I = info.value, L = levels.value[z]
  if (!I || !L) return []
  const size = (I.tile * L.mpp) / view.value.mpp          // screen px of one tile
  const a = toWorld(0, 0), b = toWorld(w.value, h.value)
  const tm = I.tile * L.mpp
  const i0 = Math.max(0, Math.floor((a.x - I.x0) / tm)), i1 = Math.min(L.nx - 1, Math.floor((b.x - I.x0) / tm))
  const j0 = Math.max(0, Math.floor((I.y1 - a.y) / tm)), j1 = Math.min(L.ny - 1, Math.floor((I.y1 - b.y) / tm))
  const out = []
  for (let j = j0; j <= j1; j++) {
    for (let i = i0; i <= i1; i++) {
      const key = `${i}_${j}`
      if (!have.value[z].has(key)) continue
      const s = toScreen(I.x0 + i * tm, I.y1 - j * tm)
      out.push({ key: `${z}/${key}`, src: `${ROOT}${z}/${key}.jpg`, left: Math.floor(s.x), top: Math.floor(s.y), size })
    }
  }
  return out
}
// the level whose pixels are the screen's or a little finer
const level = computed(() => {
  const L = levels.value
  if (!L.length) return 0
  let z = 0
  while (z + 1 < L.length && L[z + 1].mpp <= view.value.mpp * 1.2) z++
  return z
})
const tiles = computed(() => tilesOf(level.value))
const underTiles = computed(() => {
  const n = levels.value.length
  return n && level.value < n - 1 ? tilesOf(Math.min(n - 1, level.value + 3)) : []
})

// ---- places: a label only where it has room (the list order is alphabetical: bigger gaps first would be nicer)
const places = computed(() => (info.value ? info.value.places || [] : []))
const shownPlaces = computed(() => {
  const out = [], taken = []
  const gap = 70
  for (const p of places.value) {
    const s = toScreen(p.x, p.y)
    if (s.x < -50 || s.y < -20 || s.x > w.value + 50 || s.y > h.value + 20) continue
    const hot = hover.value === p.name
    if (!hot && taken.some(t => Math.abs(t.x - s.x) < gap * 1.6 && Math.abs(t.y - s.y) < gap * 0.35)) continue
    taken.push(s)
    out.push({ ...p, sx: s.x, sy: s.y })
  }
  return out
})
function norm(s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase() }
const found = computed(() => {
  const q = norm(query.value.trim())
  if (!q) return []
  return places.value.filter(p => norm(p.label).includes(q)).slice(0, 12)
})

const carScreen = computed(() => {
  if (!car.value) return null
  const s = toScreen(car.value.x, car.value.y)
  return { x: s.x, y: s.y, h: car.value.h }
})

// ---- moving
function clampView(v) {
  const I = info.value
  if (!I) return v
  const mpp = Math.min(maxMpp.value, Math.max(minMpp.value, v.mpp))
  const x = Math.min(I.x0 + I.width_m, Math.max(I.x0, v.x))
  const y = Math.min(I.y1, Math.max(I.y1 - I.height_m, v.y))
  return { x, y, mpp }
}
function zoomAround(sx, sy, f) {
  const p = toWorld(sx, sy)
  const mpp = view.value.mpp / f
  const v = clampView({ x: p.x - (sx - w.value / 2) * mpp, y: p.y + (sy - h.value / 2) * mpp, mpp })
  view.value = v
}
function zoomAt(e, f) {
  const r = viewEl.value.getBoundingClientRect()
  zoomAround(e.clientX - r.left, e.clientY - r.top, f)
}
function zoomBy(f) { zoomAround(w.value / 2, h.value / 2, f) }
function onWheel(e) { zoomAt(e, e.deltaY < 0 ? 1.25 : 0.8) }
function onDown(e) {
  if (e.button !== 0) return
  drag = { x: e.clientX, y: e.clientY, v: { ...view.value } }
  window.addEventListener("mousemove", onMove)
  window.addEventListener("mouseup", onUp)
}
function onMove(e) {
  if (!drag) return
  const v = drag.v
  view.value = clampView({ x: v.x - (e.clientX - drag.x) * v.mpp, y: v.y + (e.clientY - drag.y) * v.mpp, mpp: v.mpp })
}
function onUp() {
  drag = null
  window.removeEventListener("mousemove", onMove)
  window.removeEventListener("mouseup", onUp)
}
function fitAll() {
  const I = info.value
  if (!I) return
  view.value = clampView({ x: I.x0 + I.width_m / 2, y: I.y1 - I.height_m / 2,
                           mpp: Math.max(I.width_m / w.value, I.height_m / h.value) * 1.05 })
}
function centreCar() {
  if (!car.value) return
  view.value = clampView({ x: car.value.x, y: car.value.y, mpp: Math.min(view.value.mpp, 20) })
}

// ---- actions
function go(p) {
  msg.value = "Viaggio verso " + p.label + "..."
  engineLua(`ticino_worldmap and ticino_worldmap.uiGo(${JSON.stringify(p.name)}) or nil`, r => {
    if (!r || !r.ok) msg.value = (r && r.error) || "Non riuscito"
  })
}
function goFirst() { if (found.value.length) go(found.value[0]) }
function close() { engineLua("if ticino_worldmap then ticino_worldmap.close() end") }
function onKey(e) {
  if (e.target && e.target.tagName === "INPUT") {
    if (e.key === "Escape") query.value = ""
    return
  }
  if (e.key === "Escape" || e.key === "m" || e.key === "M") close()
  else if (e.key === "+") zoomBy(2)
  else if (e.key === "-") zoomBy(0.5)
}

function poll() {
  engineLua("ticino_worldmap and ticino_worldmap.uiState() or nil", s => {
    if (!s) return
    car.value = s.car || null
    if (!centred && info.value && car.value) {
      centred = true
      // the whole of Ticino first, as the stock map shows the whole level; the car in the middle
      fitAll()
      view.value = clampView({ ...view.value, x: car.value.x, y: car.value.y, mpp: view.value.mpp / 2 })
    }
  })
}

function measure() {
  const el = viewEl.value
  if (!el) return
  w.value = el.clientWidth || 1280
  h.value = el.clientHeight || 720
}

onMounted(() => {
  measure()
  if (window.ResizeObserver) {
    resizeObs = new ResizeObserver(measure)
    resizeObs.observe(viewEl.value)
  }
  engineLua("if ticino_worldmap then ticino_worldmap.uiOpened() end")
  engineLua("ticino_worldmap and ticino_worldmap.uiInfo() or nil", r => {
    if (!r || r.missing) { msg.value = "Mappa non trovata nel livello (levels/ticino/map)"; return }
    info.value = r
    fitAll()
    poll()
  })
  pollTimer = setInterval(poll, 500)
  nextTick(() => rootEl.value && rootEl.value.focus())
})

onUnmounted(() => {
  clearInterval(pollTimer)
  if (resizeObs) resizeObs.disconnect()
  onUp()
  typing(false)
  engineLua("if ticino_worldmap then ticino_worldmap.uiClosed() end")
})
</script>

<style scoped>
.tmap { position: absolute; inset: 0; background: rgb(38, 40, 42); color: #f2f2f2; font-family: inherit;
  overflow: hidden; outline: none; user-select: none; }
.view { position: absolute; inset: 0; overflow: hidden; cursor: grab; }
.view:active { cursor: grabbing; }
.tile { position: absolute; pointer-events: none; image-rendering: auto; }
.place { position: absolute; transform: translate(-4px, -4px); cursor: pointer; white-space: nowrap; z-index: 2; }
.place .dot { width: 8px; height: 8px; border-radius: 50%; background: #fff; box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.7); }
.place .label { position: absolute; left: 12px; top: -7px; font-size: 13px; font-weight: 600;
  text-shadow: 0 0 3px #000, 0 0 3px #000, 0 1px 2px #000; }
.place.hot { z-index: 4; }
.place.hot .dot { background: #ffcc33; }
.place.hot .label { color: #ffdd66; font-size: 15px; }
.car { position: absolute; z-index: 5; pointer-events: none; }
.car .arrow { width: 0; height: 0; margin: -13px 0 0 -9px; border-left: 9px solid transparent;
  border-right: 9px solid transparent; border-bottom: 26px solid #ff4040; transform-origin: 9px 13px;
  filter: drop-shadow(0 0 2px #000) drop-shadow(0 0 1px #fff); }
.top { position: absolute; top: 12px; left: 12px; right: 12px; display: flex; gap: 8px; align-items: center; z-index: 6; }
.title { font-size: 22px; font-weight: 700; padding: 4px 12px; background: rgba(0, 0, 0, 0.6); border-radius: 6px; }
.search { width: 260px; font-size: 15px; padding: 6px 10px; border-radius: 6px; border: 1px solid #666;
  background: rgba(20, 20, 20, 0.85); color: #fff; }
.btn { min-width: 34px; height: 32px; font-size: 18px; border-radius: 6px; border: 1px solid #666;
  background: rgba(20, 20, 20, 0.85); color: #fff; cursor: pointer; }
.btn.wide { font-size: 14px; padding: 0 10px; }
.btn:hover { background: rgba(70, 70, 70, 0.9); }
.results { position: absolute; top: 52px; left: 112px; width: 300px; max-height: 60%; overflow-y: auto; z-index: 7;
  background: rgba(20, 20, 20, 0.92); border-radius: 6px; }
.result { padding: 6px 10px; cursor: pointer; font-size: 14px; }
.result:hover { background: rgba(255, 204, 51, 0.25); }
.result.none { color: #aaa; cursor: default; }
.msg { position: absolute; top: 56px; right: 12px; padding: 6px 12px; background: rgba(0, 0, 0, 0.7); border-radius: 6px;
  z-index: 6; }
.bottom { position: absolute; left: 0; right: 0; bottom: 0; padding: 6px 12px; display: flex; justify-content: space-between;
  gap: 20px; font-size: 12px; background: rgba(0, 0, 0, 0.55); z-index: 6; }
.credits { color: #bbb; }
</style>
