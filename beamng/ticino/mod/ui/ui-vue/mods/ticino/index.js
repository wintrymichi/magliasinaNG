import { lua } from "@/bridge"

// Ticino map: a full-screen route of its own ("ticinoMap"), opened by M or the pause menu's Map in the level ticino
// (lua/ge/extensions/ticino/worldmap.lua points freeroam_bigMapMode's toggleBigMap / enterBigMap at it). The way of
// registering the route is BeamNG.Earth's (c) 2026 TecnaGamer, MIT licence (ui/ui-vue/mods/beamngEarth/index.js),
// after ui/ui-vue/mods/README.md "Standalone routes".
const SOURCE = "ticino.routes"

function routes(TicinoMap) {
  return [
    {
      path: "/ticino-map",
      name: "ticinoMap",
      component: TicinoMap,
      meta: { luaRoute: { title: "Ticino", backTarget: "play" } },
    },
  ]
}

export async function onLoad() {
  try {
    if (!window.bngRoutes || !lua.extensions.ui_router_routeManager) return
    const list = routes((await import("./TicinoMap.vue")).default)
    window.bngRoutes.add([{ path: SOURCE, routes: list }])
    const result = await lua.extensions.ui_router_routeManager.registerModRoutes(
      SOURCE, list.map(r => ({ name: r.name, path: r.path, meta: r.meta })))
    if (!result?.success) {
      window.bngRoutes.remove([SOURCE])
      console.error("Ticino: map route not registered", result?.errors)
    }
  } catch (e) {
    console.error("Ticino: map route failed", e)
  }
}

export async function onUnload() {
  try {
    if (window.bngRoutes) window.bngRoutes.remove([SOURCE])
    if (lua.extensions.ui_router_routeManager) {
      await lua.extensions.ui_router_routeManager.unregisterModRoutes(SOURCE, { fallbackRoute: "play" })
    }
  } catch (e) {
    console.error("Ticino: map unload failed", e)
  }
}
