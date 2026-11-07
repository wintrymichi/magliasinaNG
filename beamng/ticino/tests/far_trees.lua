-- Outside the game: the far trees of objects.lua (fine tiles near, coarse blocks beyond, fartrees.py) on a made-up map.
-- Along a drive and a teleport, once the queue is made and the covers dropped, every tile with far trees between the
-- Forest's rings and the radius must be drawn by exactly one shown entry (a fine tile or its coarse block); tiles inside
-- the Forest's rings by none (the Forest draws them). While a change goes on a tile may be drawn twice, never by none.
--   python3 tests/luajit.py tests/far_trees.lua     (pip install lupa)
EXT = (arg and arg[0] or ''):gsub('[^/]*$', '') .. '../mod/lua/ge/extensions'
package.path = EXT .. '/?.lua;' .. package.path
local nextId, objs = 1, {}
function log(l, t, m) if l ~= 'I' or os.getenv('LOGI') then print(l, m) end end
local Obj = {}
Obj.__index = Obj
function Obj:setField(k, i, v) self.f[k] = v end
function Obj:setPosition(p) self.pos = p end
function Obj:registerObject() self.reg = true end
function Obj:getID() return self.id end
function Obj:setHidden(h) self.hidden = h end
function Obj:delete() objs[self.id] = nil end
function createObject(c)
  local o = setmetatable({ id = nextId, cls = c, f = {} }, Obj); nextId = nextId + 1; objs[o.id] = o; return o
end
scenetree = { findObjectById = function(id) return objs[id] end, MissionGroup = { addObject = function() end } }
function vec3(x, y, z) return { x = x, y = y, z = z } end
function readFile() return nil end
function jsonDecode() return nil end
local objects = require('ticino/objects')

local N, M, B = 160, 120, 4
local ft, has, blk = {}, {}, {}
for y = -20, M - 1 do
  for x = -20, N - 1 do
    if not (x > 90 and y > 60) and (x * 7 + y * 3) % 11 ~= 0 then   -- some tiles with no trees
      ft[#ft + 1] = x .. '_' .. y; has[x .. '_' .. y] = true
      blk[math.floor(x / B) .. '_' .. math.floor(y / B)] = true
    end
  end
end
local ft2 = {}
for k in pairs(blk) do ft2[#ft2 + 1] = k end
local cfg = { tiles = {}, forestTiles = {}, maxRadius = 6, origin = { 0, 0 }, cell = 256, square = 1.5,
              farTrees = ft, farTrees2 = ft2, farTrees2Tiles = B }
objects.init(cfg, 'L', { addObject = function() end })
local t = 0
local function clock() t = t + 1; return t end
local forestHas = {}                     -- tiles the made-up Forest shows
objects.forestMade = function(key) return forestHas[key] == true end
objects.FAR_TREES_HOLD_MS = 1e9

local bad, doubles = 0, 0
local before = {}                        -- tiles covered when the last move settled
local beforeForest = {}
local function check(what, cx, cy, settled)
  local cover = {}
  for _, o in pairs(objs) do
    if o.reg and not o.hidden then
      local s = o.f.shapeName
      local x, y = s:match('/t_(%-?%d+)_(%-?%d+)%.cdae$')
      if x then
        local k = x .. '_' .. y
        cover[k] = (cover[k] or 0) + 1
      else
        local bx, by = s:match('/l2_(%-?%d+)_(%-?%d+)%.cdae$')
        bx, by = tonumber(bx), tonumber(by)
        for ty = by * B, by * B + B - 1 do
          for tx = bx * B, bx * B + B - 1 do
            local k = tx .. '_' .. ty
            if has[k] then cover[k] = (cover[k] or 0) + 1 end
          end
        end
      end
    end
  end
  local R, I = objects.FAR_TREES_RADIUS, objects.FAR_TREES_INNER
  local holes, two, inner = 0, 0, 0
  for k in pairs(has) do
    local x, y = k:match('^(%-?%d+)_(%-?%d+)$')
    local d = math.max(math.abs(tonumber(x) - cx), math.abs(tonumber(y) - cy))
    local c = cover[k] or 0
    -- settled: everything in the ring drawn; during a move: nothing that was drawn before lost without its cover
    local want = d <= R and (settled or before[k])
    if d > I and want and c == 0 and not forestHas[k] then
      holes = holes + 1
      if os.getenv('WHY') then print('  hole', k, 'd', d, 'beforeForest', tostring(beforeForest[k])) end
    end
    if d <= I and want and c == 0 and not forestHas[k] then holes = holes + 1 end
    if c > 1 then two = two + 1 end
    if settled and d <= I - 0 and c > 0 then inner = inner + 1 end
  end
  if holes > 0 or (settled and (two > 0 or inner > 0)) then
    bad = bad + 1
    print(string.format('BAD %s at %d,%d: %d holes, %d doubled, %d drawn inside the Forest', what, cx, cy, holes, two, inner))
  end
  if two > 0 then doubles = doubles + 1 end
  if settled then
    before = {}
    for k in pairs(has) do
      if (cover[k] or 0) > 0 or forestHas[k] then before[k] = true end
      beforeForest[k] = (cover[k] or 0) == 0 and forestHas[k] or nil
    end
  end
end

-- keep: the old rings stay (the Forest drops a tile in a later pass than the far trees take it over)
local function forestAround(cx, cy, keep)
  if not keep then forestHas = {} end
  for y = cy - objects.FAR_TREES_INNER, cy + objects.FAR_TREES_INNER do
    for x = cx - objects.FAR_TREES_INNER, cx + objects.FAR_TREES_INNER do forestHas[x .. '_' .. y] = true end
  end
end

-- a move: the queue made a few at a time, the Forest arriving late; check every frame, settled at the end
local function go(what, cx, cy)
  objects.updateFarTrees(cx, cy)
  local frames = 0
  while objects.farTreesPending() or objects.farTreesHeld() do
    objects.stepFarTrees(clock, 3)
    frames = frames + 1
    if frames == 5 then forestAround(cx, cy, true) end
    check(what, cx, cy, false)
    if frames > 5000 then print('BAD stuck', what) bad = bad + 1 break end
  end
  forestAround(cx, cy)
  objects.dropFarTrees(clock)
  check(what .. ' settled', cx, cy, true)
end

forestAround(20, 26)
go('start', 20, 26)
for x = 21, 70 do go('drive', x, 20 + math.floor(x / 3)) end
before = {}
go('jump', 100, 30)
for y = 31, 60 do go('drive2', 100, y) end
-- A flight whose queue never drains (PC l_A of 1860ef2: the far trees made ~2 shapes a second, a tile change every
-- 11.6 s, and the fine tiles behind the car were never removed: 0 -> 428 live, fps 91 -> 50). One shape a frame, 20
-- frames of 580 ms a tile, the game's 20 s hold: what lives must stay near what the car's tile wants, not grow.
do
  local T = t
  local function clk() T = T + 1; return T end
  objects.FAR_TREES_HOLD_MS = 20000
  local cx, cy = 60, 0
  local function wanted()
    local n = 0
    local R, I, B0 = objects.FAR_TREES_RADIUS, objects.FAR_TREES_INNER, objects.FAR_TREES_BLOCKS0
    local bcx, bcy = math.floor(cx / B), math.floor(cy / B)
    for k in pairs(has) do
      local x, y = k:match('^(%-?%d+)_(%-?%d+)$')
      x, y = tonumber(x), tonumber(y)
      local d = math.max(math.abs(x - cx), math.abs(y - cy))
      local bd = math.max(math.abs(math.floor(x / B) - bcx), math.abs(math.floor(y / B) - bcy))
      if d > I and d <= R and bd <= B0 then n = n + 1 end
    end
    for k in pairs(blk) do
      local bx, by = k:match('^(%-?%d+)_(%-?%d+)$')
      local bd = math.max(math.abs(tonumber(bx) - bcx), math.abs(tonumber(by) - bcy))
      if bd > B0 and bd <= math.ceil(objects.FAR_TREES_RADIUS / B) then n = n + 1 end
    end
    return n
  end
  local at40, maxRatio = nil, 0
  for i = 1, 120 do
    cy = i
    forestAround(cx, cy)
    objects.updateFarTrees(cx, cy)
    for f = 1, 20 do
      T = T + 580
      objects.dropFarTrees(clk)
      objects.stepFarTrees(clk, 0)
    end
    local s = objects.stats()
    local live = s.farTrees + s.farTrees2
    local r = live / wanted()
    if r > maxRatio then maxRatio = r end
    if i == 40 then at40 = live end
    if i == 120 then
      print(string.format('starved flight: live %d at tile 40, %d at tile 120 (%d wanted), at most %.2f times what the '
        .. 'tile wants', at40, live, wanted(), maxRatio))
      if live > at40 * 1.15 or maxRatio > 1.6 then print('BAD starved flight: the far trees pile up') bad = bad + 1 end
    end
  end
  t = T
end
objects.FAR_TREES_RADIUS = 0
objects.updateFarTrees(100, 60)
local left = 0
for _, o in pairs(objs) do if o.reg then left = left + 1 end end
if left > 0 then print('BAD radius 0 left', left) bad = bad + 1 end
print(bad == 0 and 'far trees ok' or ('far trees FAILED ' .. bad), 'moves with a moment of two layers: ' .. doubles)
