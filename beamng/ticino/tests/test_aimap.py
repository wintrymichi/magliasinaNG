"""aimap.py + mod/lua/ge/extensions/ticino/aimap.lua outside the game (LuaJIT through lupa).

A small made-up network (a T junction, a road ending on another's node, two roads ending at the same point, a private
road, a tunnel road in another group, a one-way road) is written as a level scene, built with aimap.py, read back by
aimap.lua and handed to a stub of map.lua that does what loadMap does with custom nodes (convertToSingleSided, then
one graph edge per link from inNode to outNode). Checked: every road is linked into one piece, the junction nodes
are shared, lanes and one-way sense survive, private links are gated, map.load / assureLoad / reset and the
onNavgraphReloaded fallback all end with the file's graph.

    python tests/test_aimap.py [<aimap.bin of a real level>]   (with a file: parse + tables time on the real graph)
"""
import json
import os
import sys
import tempfile
import time

from lupa import luajit21

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import aimap  # noqa: E402

EXT = os.path.join(os.path.dirname(HERE), "mod", "lua", "ge", "extensions")


def road(name, pts, width=6.0, **kw):
    o = {"name": name, "class": "DecalRoad", "drivability": 1.0, "autoLanes": False, "lanesLeft": 1, "lanesRight": 1,
         "speedLimit": 13.89, "nodes": [[x, y, z, width] for x, y, z in pts]}
    o.update(kw)
    return o


def scene(folder):
    main = [
        road("main", [(0, 0, 100), (20, 0, 100), (40, 0, 100), (60, 0, 101), (80, 0, 102)]),
        # ends on main's node (40, 0): a T made by the welding
        road("side", [(40, 30, 103), (40, 15, 101.5), (40, 0.4, 100.1)]),
        # starts where main ends (end to end)
        road("on", [(80, 0, 102), (100, 10, 103), (120, 20, 104)]),
        # a private drive off "on"
        road("drive", [(100, 10, 103), (100, 30, 104)], width=3.0, gatedRoad=True),
        # one way (lanes on the left only: map.lua flips it)
        road("ramp", [(120, 20, 104), (140, 20, 104)], lanesLeft=2, lanesRight=0),
        # a road over main on a bridge (8 m higher): must NOT join it
        road("over", [(20, -30, 109), (20, 0, 108.5), (20, 30, 109)]),
    ]
    tunnel = [road("tun", [(140, 20, 104), (160, 20, 104), (180, 20, 104)], width=8.0, __parent="tunnels")]
    for grp, objs in (("AIRoads", main), ("tunnels", tunnel)):
        d = os.path.join(folder, "main", "MissionGroup", grp)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "items.level.json"), "w") as f:
            for o in objs:
                f.write(json.dumps(o) + "\n")


LUA_STUBS = r"""
package.path = EXT .. '/?.lua;' .. package.path
LOGS = {}
function log(l, t, m) LOGS[#LOGS + 1] = l .. ' ' .. m end
local V = {}
V.__index = V
V.__eq = function(a, b) return a.x == b.x and a.y == b.y and a.z == b.z end
function vec3(x, y, z) return setmetatable({ x = x, y = y, z = z }, V) end
function V:distance(o) return math.sqrt((self.x - o.x) ^ 2 + (self.y - o.y) ^ 2 + (self.z - o.z) ^ 2) end
MISSION = '/levels/ticino/main.level.json'
function getMissionFilename() return MISSION end
function readFile(p)
  local f = io.open(FILES[p] or '', 'rb')
  if not f then return nil end
  local s = f:read('*a'); f:close(); return s
end
-- map.lua stub: loadMap(custom) -> convertToSingleSided -> graph; its own loadMap (no DecalRoads) -> empty
HOOKS = {}
local function loadMap(custom)
  local nodes = custom or {}
  local g, ec = {}, 0
  for nid, n in pairs(nodes) do
    local newLinks = {}
    for lid, d in pairs(n.links) do
      if d.inNode == lid then newLinks[lid] = d; ec = ec + 1 end
    end
    n.links = newLinks
  end
  for nid, n in pairs(nodes) do
    for lid, d in pairs(n.links) do
      g[#g + 1] = { d.inNode, d.outNode, d }
    end
  end
  map._nodes, map._edges = nodes, g
  map.loads = (map.loads or 0) + 1
  for _, h in ipairs(HOOKS) do h() end
end
map = { reset = loadMap, load = function() loadMap() end, assureLoad = function() loadMap() end,
        getMap = function() return { nodes = map._nodes or {} } end }
"""


def runtime(files):
    rt = luajit21.LuaRuntime()
    g = rt.globals()
    g.EXT = EXT
    g.FILES = rt.table_from(files)
    g.jsonDecode = lambda s: rt.table_from(json.loads(s), recursive=True)
    rt.execute(LUA_STUBS)
    return rt


def check_small():
    with tempfile.TemporaryDirectory() as tmp:
        scene(tmp)
        out = os.path.join(tmp, "ai", "aimap.bin")
        rep = aimap.build(tmp, out)
        assert rep["pieces"] == 2, rep            # the network + the bridge road over it
        rt = runtime({"/levels/ticino/ai/aimap.bin": out})
        res = rt.execute(r"""
local aimap = require('ticino/aimap')
aimap.install()
HOOKS[1] = aimap.onNavgraphReloaded
local r = {}
map.load()                              -- level loading: the file's graph
r.afterLoad = #map._edges
map._edges = {}
map.load()                              -- loaded once per mission: no second build
r.secondLoad = #map._edges
map.reset()                             -- anyone's map.reset(): the file again
r.afterReset = #map._edges
-- map.lua's own loadMap (editor, map.json change) finds no DecalRoads: the hook puts the graph back
local inner = map.reset
map._edges = {}; map._nodes = {}
for _, h in ipairs(HOOKS) do h() end
r.afterHook = #map._edges
r.loads = aimap.stats().loads
-- the graph's content
local nodes = map._nodes
local deg, priv, gated, oneway, lanes = {}, 0, 0, 0, {}
for nid, n in pairs(nodes) do
  for lid, d in pairs(n.links) do
    deg[nid] = (deg[nid] or 0) + 1; deg[lid] = (deg[lid] or 0) + 1
    if d.type == 'private' then priv = priv + 1 end
    if d.gatedRoad then gated = gated + 1 end
    if d.oneWay then oneway = oneway + 1; lanes[#lanes + 1] = d.lanes .. '@' .. d.inPos.x .. '>' .. d.outPos.x end
    assert(d.inPos == nodes[d.inNode].pos and d.outPos == nodes[d.outNode].pos)
    assert(d.speedLimit > 13 and d.speedLimit < 14)
  end
end
local j3 = 0
for _, c in pairs(deg) do if c >= 3 then j3 = j3 + 1 end end
r.junctions, r.priv, r.gated, r.oneway, r.lanes = j3, priv, gated, oneway, table.concat(lanes, ' ')
-- another level: untouched
MISSION = '/levels/italy/main.level.json'
aimap.onClientEndMission()
map._edges = {}
map.load()
r.otherLevel = #map._edges
return r
""")
        r = {k: res[k] for k in res}
        print("small network:", r)
        assert r["afterLoad"] > 0 and r["secondLoad"] == 0 and r["afterReset"] == r["afterLoad"], r
        assert r["afterHook"] == r["afterLoad"] and r["loads"] == 3, r
        assert r["junctions"] == 2, r            # the T at (40,0) and the drive at (100,10)
        assert r["priv"] == 1 and r["gated"] >= 1, r
        assert r["oneway"] >= 1 and r["lanes"].startswith("++@140>120"), r
        assert r["otherLevel"] == 0, r


def check_file(path):
    rt = runtime({"/levels/ticino/ai/aimap.bin": path})
    t0 = time.time()
    res = rt.execute(r"""
local aimap = require('ticino/aimap')
local t0 = os.clock()
local g = aimap.parse(readFile('/levels/ticino/ai/aimap.bin'))
local t1 = os.clock()
local nodes = aimap.toNodes(g)
local t2 = os.clock()
local n, e = 0, 0
for _, v in pairs(nodes) do n = n + 1; for _ in pairs(v.links) do e = e + 1 end end
return { parse = (t1 - t0) * 1000, tables = (t2 - t1) * 1000, nodes = n, links = e, mem = collectgarbage('count') / 1024 }
""")
    print("real file: parse %.0f ms, tables %.0f ms, %d nodes, %d link entries, Lua heap %.0f MB (%.1f s)"
          % (res["parse"], res["tables"], res["nodes"], res["links"], res["mem"], time.time() - t0))


if __name__ == "__main__":
    check_small()
    if len(sys.argv) > 1:
        check_file(sys.argv[1])
    print("ok")
