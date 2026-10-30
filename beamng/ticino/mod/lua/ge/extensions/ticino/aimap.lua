-- The AI graph of the Ticino level, made at build time (beamng/ticino/aimap.py) and handed to the game's map.lua as
-- ready nodes: the level has no AI DecalRoads, so the game's own graph is empty until this one is loaded.
--
-- Why: map.lua builds its graph from the AI DecalRoads clipped to the terrain, and the terrain is only the 3 km window
-- round the car: every node outside it lay at z 0, findClosestRoad found nothing there, 4,020 of 4,065 signals failed
-- ("Map node could not be set") and traffic ran only near the spawn; map.reset over the 57,298 roads took 28-30 s.
--
-- File (aimap.py): b"TAIM", u32 version, u32 nodes, u32 edges, u32 types, nodes f32 x y z radius, edges u32 in, u32
-- out, u16 type, u16 flags (bit0 oneWay, bit1 gated), u32 length + json [[drivability, speedLimit, lanes], ...].

local ffi = require('ffi')

local M = {}

M.FILE = '/levels/ticino/ai/aimap.bin'

local function u32(s, o)
  local a, b, c, d = s:byte(o + 1, o + 4)
  return a + b * 256 + c * 65536 + d * 16777216
end

-- The file as plain Lua data: { n, m, pos = float array (x, y, z, r per node), ein, eout, etype, eflags, types }.
-- `data` is the file's bytes (a string); the arrays are copies, so the string may go.
function M.parse(data)
  if type(data) ~= 'string' or #data < 20 or data:sub(1, 4) ~= 'TAIM' then return nil, 'not an aimap file' end
  local ver, n, m, nt = u32(data, 4), u32(data, 8), u32(data, 12), u32(data, 16)
  if ver ~= 1 then return nil, 'aimap version ' .. ver end
  local o = 20
  local need = o + n * 16 + m * 12 + 4
  if #data < need then return nil, 'aimap file cut short' end
  local base = ffi.cast('const uint8_t *', data)
  local pos = ffi.new('float[?]', n * 4)
  ffi.copy(pos, base + o, n * 16)
  o = o + n * 16
  local ein, eout = ffi.new('uint32_t[?]', m), ffi.new('uint32_t[?]', m)
  local etype, eflags = ffi.new('uint16_t[?]', m), ffi.new('uint16_t[?]', m)
  local ep = ffi.cast('const uint8_t *', base + o)
  for k = 0, m - 1 do
    local q = ep + k * 12
    ein[k] = ffi.cast('const uint32_t *', q)[0]
    eout[k] = ffi.cast('const uint32_t *', q + 4)[0]
    etype[k] = ffi.cast('const uint16_t *', q + 8)[0]
    eflags[k] = ffi.cast('const uint16_t *', q + 10)[0]
  end
  o = o + m * 12
  local ln = u32(data, o)
  local types = (jsonDecode or require('json').decode)(data:sub(o + 5, o + 4 + ln))
  if type(types) ~= 'table' or #types ~= nt then return nil, 'aimap types unreadable' end
  return { n = n, m = m, pos = pos, ein = ein, eout = eout, etype = etype, eflags = eflags, types = types }
end


-- The graph as map.lua's linkMap leaves it before convertToSingleSided: nodes { pos, radius, links = { [other] = edge } }
-- with each edge table shared by its two nodes, edge fields as loadJsonDecalMap writes them (inPos/outPos are the
-- nodes' own vec3, so loadMap passes no offsets to graphpath). Private roads as processPrivateRoads marks them.
function M.toNodes(g)
  local pos = g.pos
  local ok, tnew = pcall(require, 'table.new')
  local names = {}
  local nodes = ok and tnew(0, g.n) or {}
  for i = 0, g.n - 1 do
    local nid = 't' .. i
    names[i] = nid
    local o = 4 * i
    nodes[nid] = { pos = vec3(pos[o], pos[o + 1], pos[o + 2]), radius = pos[o + 3], links = {} }
  end
  local types = g.types
  for k = 0, g.m - 1 do
    local a, b = names[g.ein[k]], names[g.eout[k]]
    local na, nb = nodes[a], nodes[b]
    local t = types[g.etype[k] + 1]
    local f = g.eflags[k]
    local edge = {
      drivability = t[1], speedLimit = t[2], lanes = t[3], oneWay = f % 2 == 1,
      type = (math.floor(f / 2) % 2 == 1) and 'private' or nil,
      inNode = a, outNode = b, inPos = na.pos, outPos = nb.pos, inRadius = na.radius, outRadius = nb.radius,
    }
    na.links[b] = edge
    nb.links[a] = edge
  end
  -- processPrivateRoads: where private links meet public ones, the gate goes on the single public link or on the
  -- private ones
  for _, n in pairs(nodes) do
    local priv, count = 0, 0
    for _, d in pairs(n.links) do
      if d.type == 'private' then priv = priv + 1 end
      count = count + 1
    end
    if priv > 0 and priv < count then
      for _, d in pairs(n.links) do
        if (priv == count - 1) == (d.type ~= 'private') then d.gatedRoad = true end
      end
    end
  end
  return nodes
end

-- ------------------------------------------------------------------ hooking into map.lua
local graph = nil          -- the parsed file of this level (kept: map.lua changes the node tables it is given)
local origReset, origLoad, origAssure = nil, nil, nil
local stats = { loads = 0 }

local function clock()
  return os.clock() * 1000
end

-- Is this level's graph in use? (the level ticino with its ai/aimap.bin)
function M.active()
  local mf = getMissionFilename and getMissionFilename() or ''
  if not mf:find('/levels/ticino/', 1, true) then return false end
  if graph == nil then
    local t0 = clock()
    local data = readFile and readFile(M.FILE)
    if not data then
      graph = false
      log('W', 'ticino', 'no ' .. M.FILE .. ': the AI map comes from the scene\'s DecalRoads')
    else
      local g, err = M.parse(data)
      graph = g or false
      if g then
        stats.parseMs = clock() - t0
        log('I', 'ticino', string.format('AI map file: %d nodes, %d edges (%.0f ms)', g.n, g.m, stats.parseMs))
      else
        log('E', 'ticino', 'AI map file unreadable: ' .. tostring(err))
      end
    end
  end
  return graph and true or false
end

local function nodesNow()
  local t0 = clock()
  local nodes = M.toNodes(graph)
  stats.buildMs = clock() - t0
  return nodes
end

local function resetWith(custom)
  if custom == nil and M.active() then
    local nodes = nodesNow()
    local t0 = clock()
    origReset(nodes)
    stats.loads = stats.loads + 1
    stats.loadMs = clock() - t0
    log('I', 'ticino', string.format('AI map loaded from the file: tables %.0f ms, map.lua %.0f ms',
      stats.buildMs or 0, stats.loadMs))
    return
  end
  return origReset(custom)
end

-- Wraps map.reset / map.load / map.assureLoad: in the level ticino they load the file's graph. Their own loadMap
-- (called inside map.lua, e.g. by the editor) finds no AI DecalRoads; onNavgraphReloaded then puts the graph back.
function M.install()
  if not map or not map.reset or map.reset == resetWith then return end
  origReset, origLoad, origAssure = map.reset, map.load, map.assureLoad
  local loaded = false
  map.reset = resetWith
  map.load = function(...)
    if not M.active() then return origLoad(...) end
    if loaded then return end
    loaded = true
    resetWith(nil)
  end
  map.assureLoad = function(...)
    if not M.active() then return origAssure(...) end
    if not loaded then resetWith(nil) end
    loaded = false
  end
  M._missionLoaded = function() loaded = false end
end

function M.uninstall()
  if not origReset or not map then return end
  map.reset, map.load, map.assureLoad = origReset, origLoad, origAssure
  origReset, origLoad, origAssure = nil, nil, nil
end

-- onNavgraphReloaded: a graph with no node in the level ticino came from map.lua's own loadMap (no DecalRoads)
function M.onNavgraphReloaded()
  if map and map.reset ~= resetWith then M.install() end
  if not origReset or not M.active() then return end
  local m = map.getMap and map.getMap()
  if m and m.nodes and next(m.nodes) == nil then resetWith(nil) end
end

-- a new level: read its file again
function M.onClientEndMission()
  graph = nil
  if M._missionLoaded then M._missionLoaded() end
end

function M.stats()
  return { loads = stats.loads, parseMs = stats.parseMs, buildMs = stats.buildMs, loadMs = stats.loadMs,
           nodes = graph and graph.n or 0, edges = graph and graph.m or 0 }
end

return M
