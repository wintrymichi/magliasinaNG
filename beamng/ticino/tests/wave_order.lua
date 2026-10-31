-- Outside the game: the order of the wave (objects.lua, forest.lua) on a made-up grid of tiles. After a move the
-- near rings must come first and never again after a farther one, and the end state must equal a fresh jump there.
--   luajit wave_order.lua      (no luajit in the cloud container: pip install lupa, then
--   python3 -c "import sys; from lupa import luajit21 as l; r = l.LuaRuntime(); r.globals().arg = r.table('wave_order.lua'); r.execute(open('wave_order.lua').read())")
EXT = (arg and arg[0] or ''):gsub('[^/]*$', '') .. '../mod/lua/ge/extensions'
package.path = EXT .. '/?.lua;' .. package.path
local nextId, objs = 1, {}
function log(l, t, m) if l ~= 'I' then print(l, m) end end
local Obj = {}
Obj.__index = Obj
function Obj:setField() end
function Obj:setPosition() end
function Obj:registerObject() end
function Obj:setPosRot() end
function Obj:setScale() end
function Obj:getID() return self.id end
function Obj:delete() objs[self.id] = nil; DELETED = DELETED + 1 end
function Obj:getData() return self.fd end
function createObject(c)
  local o = setmetatable({ id = nextId, cls = c }, Obj); nextId = nextId + 1; objs[o.id] = o
  if c == 'Forest' then o.fd = { n = 0, createNewItem = function(s) s.n = s.n + 1; return { } end, removeItem = function(s) s.n = s.n - 1 end } end
  CREATED[#CREATED + 1] = o; return o
end
DELETED = 0; CREATED = {}
scenetree = { findObjectById = function(id) return objs[id] end, findObject = function(n) return setmetatable({ id = 0, getField = function() return '' end }, Obj) end, MissionGroup = { addObject = function() end } }
function vec3(x, y, z) return { x = x, y = y, z = z } end
function MatrixF() return { setFromEuler = function() end, setPosition = function() end } end
TILES = {}
function readFile(p) return p end
function jsonDecode(p) local t = TILES[p]; if not t then error('no ' .. p) end; return t end
local objects = require('ticino/objects')
local forest = require('ticino/forest')
-- tiles: each with entries: one building (r 6), one road (r 5, collides), clutter (r 2)
local cfg = { tiles = {}, forestTiles = {}, maxRadius = 6, collisionRadius = 1, origin = { 0, 0 }, forestTypes = { 'oak' } }
for x = -12, 12 do for y = -12, 12 do
  local k = x .. '_' .. y
  cfg.tiles[k] = true; cfg.forestTiles[k] = true
  TILES[string.format('/levels/L/tiles/o_%d_%d.json', x, y)] = {
    { class = 'TSStatic', p = { 0, 0, 0 }, r = 6, shapeName = 'bld', collisionType = 'None', tx = x, ty = y },
    { class = 'TSStatic', p = { 0, 0, 0 }, r = 5, shapeName = 'road', tx = x, ty = y },
    { class = 'TSStatic', p = { 0, 0, 0 }, r = 2, shapeName = 'clutter_pallet', tx = x, ty = y } }
  local rows = {}
  for i = 1, 100 do rows[i] = { 0, 1, 2, 3, 0, 1 } end
  TILES[string.format('/levels/L/tiles/t_%d_%d.trees.json', x, y)] = rows
end end
objects.init(cfg, 'L', { addObject = function() end })
forest.init(cfg, 'L', function() end)
forest.BLOCK = tonumber(os.getenv('BLOCK') or '1')
forest.HYST = 0   -- the end state below is a fresh jump's; the hysteresis is checked at the end
local t = 0
local clock = function() t = t + 0.01; return t end
-- jump at 0,0
objects.retarget(0, 0); objects.step(clock, nil)
forest.retarget(0, 0); forest.step(clock, nil, 1e9)
local s = objects.stats(); print('after jump live', s.live, 'colliders', s.colliders, 'forest', forest.stats().items)
-- move one tile east; record the ring order of creations
CREATED = {}
local n = objects.retarget(1, 0)
print('queued', n)
local order, sawFar, bad = {}, false, 0
while objects.pending() do
  local near = objects.nearPending(1)
  objects.step(clock, 0.001)
  for _, o in ipairs(CREATED) do end
end
-- check ordering by looking at queue prios already consumed: rebuild via a second move with inspection
local live = objects.stats(); print('after move live', live.live, 'colliders', live.colliders, 'deleted', DELETED)
-- forest wave
local fq = forest.retarget(1, 0)
local passes = {}
print('forest passes', fq)
while forest.pending() do forest.step(clock, nil, 50) end
print('forest items', forest.stats().items)
-- expected: same as a fresh jump at 1,0
local fresh = 0
for dx = -4, 4 do for dy = -4, 4 do
  local d = math.max(math.abs(dx), math.abs(dy))
  local sh = forest.SHARE[d]
  for i = 1, 100 do local v = i * 0.6180339887; if sh >= 1 or v - math.floor(v) < sh then fresh = fresh + 1 end end
end end
print('expected forest items', fresh)
-- expected objects at 1,0: bld within 6 (13x13), road within 5 (11x11), clutter within 2 (5x5)
print('expected live', 169 + 121 + 25)
-- ordering: move again (2,1); nearPending must go true...false and never back; first ops are near
objects.retarget(2, 1)
local seq = {}
while objects.pending() do seq[#seq + 1] = objects.nearPending(1) and 'N' or 'f'; objects.step(clock, -1) end
local o = table.concat(seq)
assert(o:match('^N+f*$'), 'objects: a near ring after a farther one: ' .. o)
print('objects order', o)
forest.retarget(2, 1)
seq = {}
while forest.pending() do seq[#seq + 1] = forest.nearPending() and 'N' or 'f'; forest.step(clock, nil, 1) end
local str = table.concat(seq)
assert(str:match('^N+f*$'), 'forest: a near ring after a farther one')
print('forest order', #str:gsub('f', ''), 'near steps, then', #str:gsub('N', ''))
print('final', objects.stats().live, forest.stats().items)
assert(live.live == 315 and objects.stats().live == 315, 'objects end state')
assert(forest.stats().items == fresh, 'forest end state')
-- hysteresis: one tile on and back again passes only the tiles that must grow or collide, never one that thins
forest.HYST = 1
forest.retarget(3, 1); while forest.pending() do forest.step(clock, nil, 1e9) end
local before = forest.stats().items
local nback = forest.retarget(2, 1)
while forest.pending() do forest.step(clock, nil, 1e9) end
assert(forest.stats().items >= before, 'hysteresis: a tile thinned on the way back')
print('hysteresis: back one tile', nback, 'passes, items', before, '->', forest.stats().items)
-- frames that touch a Forest on a move (budget mode, as the streamer calls it): fewer with BLOCK > 1
local t0 = forest.counts().touched
forest.retarget(4, 2)
local frames = 0
while forest.pending() do frames = frames + 1; forest.step(clock, 3) end
print('move: frames', frames, 'Forests touched', forest.counts().touched - t0, 'BLOCK', forest.BLOCK)
print('OK')
