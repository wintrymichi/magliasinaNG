-- Outside the game: the far levels of objects.lua (the far tiles' quadtree, farlod.py) on a made-up map. At every frame
-- of a drive and of a teleport, each far tile of the map must be drawn by exactly one shown entry (a far tile, a coarse
-- tile, or the terrain window), never by none (a hole) and never by two (two layers fighting).
--   python3 tests/luajit.py tests/far_lod.lua     (pip install lupa)
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

-- the map: far tiles in an L shape with a hole, 120 x 90 tiles; coarse levels where any far tile is
local N, M = 120, 90
local far, has = {}, {}
for y = 0, M - 1 do
  for x = 0, N - 1 do
    local out = (x > 70 and y > 50) or (x >= 30 and x < 34 and y >= 20 and y < 24)
    if not out then far[#far + 1] = x .. '_' .. y; has[x .. '_' .. y] = true end
  end
end
local lod = {}
for k = 2, 5 do
  local s, set = 2 ^ k, {}
  for key in pairs(has) do
    local x, y = key:match('^(%-?%d+)_(%-?%d+)$')
    set[math.floor(tonumber(x) / s) .. '_' .. math.floor(tonumber(y) / s)] = true
  end
  lod[tostring(k)] = {}
  for key in pairs(set) do table.insert(lod[tostring(k)], key) end
end
local cfg = { tiles = {}, forestTiles = {}, maxRadius = 6, origin = { 0, 0 }, cell = 256, square = 1.5, far = far,
              farRadius = 16, farLod = lod,
              -- FAR_FINE=1: the base's level 0 tiles (farlod.build_fine) instead of the slices' far tiles
              farFine = os.getenv('FAR_FINE') and 'farlod/l0_%d_%d.cdae' or nil }
local group = { addObject = function() end }
objects.init(cfg, 'L', group)
local t = 0
local function clock() t = t + 0.01; return t end

-- every far tile covered once: by the window (8 x 8 from wcx, wcy) or by one shown entry
local bad = 0
local function check(what, wcx, wcy)
  local cover = {}
  for _, o in pairs(objs) do
    if o.cls == 'TSStatic' and o.reg and not o.hidden then
      local k, i, j = o.f.shapeName:match('/l(%d)_(%-?%d+)_(%-?%d+)%.cdae$')
      local x0, y0, s
      if k then
        s = 2 ^ tonumber(k); x0, y0 = tonumber(i) * s, tonumber(j) * s
      else
        local a, b = o.f.shapeName:match('f_(%-?%d+)_(%-?%d+)%.cdae$')
        s, x0, y0 = 1, tonumber(a), tonumber(b)
      end
      for y = y0, y0 + s - 1 do
        for x = x0, x0 + s - 1 do
          local key = x .. '_' .. y
          cover[key] = (cover[key] or 0) + 1
        end
      end
    end
  end
  for y = wcy, wcy + 7 do for x = wcx, wcx + 7 do local key = x .. '_' .. y; cover[key] = (cover[key] or 0) + 1 end end
  local holes, double = 0, 0
  for key in pairs(has) do
    local c = cover[key] or 0
    if c == 0 then holes = holes + 1 elseif c > 1 then double = double + 1 end
  end
  if holes > 0 or double > 0 then
    bad = bad + 1
    if bad < 8 then print(string.format('%s: %d holes, %d doubled', what, holes, double)) end
  end
  return holes, double
end

local function count()
  local n, nl = 0, 0
  for _, o in pairs(objs) do if o.cls == 'TSStatic' then n = n + 1; if o.f.shapeName:find('/l[1-9]_') then nl = nl + 1 end end end
  return n, nl
end

-- a jump: everything made at once, then checked
local cx, cy = 20, 20
local wcx, wcy = cx - 3, cy - 3
objects.updateFar(cx, cy, wcx, wcy, 8)
objects.stepFar(clock, nil)
check('jump', wcx, wcy)
local n, nl = count()
print(string.format('after the jump: %d far entries, %d of them coarse', n, nl))
assert(nl > 0 and nl < 400, 'coarse count ' .. nl)

-- a drive east and north: a tile change every 40 frames, a few entries made a frame, checked every frame
local frames = 0
for step = 1, 70 do
  if step <= 45 then cx = cx + 1 else cy = cy + 1 end
  if cx - wcx > 5 then wcx = cx - 2 end
  if cy - wcy > 5 then wcy = cy - 2 end
  objects.updateFar(cx, cy, wcx, wcy, 8)
  for f = 1, 40 do
    frames = frames + 1
    if objects.farPending() then
      local t0 = t
      objects.stepFar(function() t = t + 0.4; return t end, 1)   -- ~3 entries a frame
    end
    objects.dropCovered(clock, false)
    check(string.format('drive step %d frame %d (car %d,%d)', step, f, cx, cy), wcx, wcy)
  end
end
-- the end state must be what a fresh jump there gives
while objects.farPending() do objects.stepFar(clock, nil) end
objects.dropCovered(clock, true)
local n1, nl1 = count()
check('end', wcx, wcy)
assert(not objects.farDoomedLeft(), 'old entries left at the end')
-- a teleport across the map
cx, cy = 100, 10; wcx, wcy = cx - 3, cy - 3
objects.updateFar(cx, cy, wcx, wcy, 8)
for f = 1, 400 do
  if objects.farPending() then objects.stepFar(function() t = t + 0.4; return t end, 1) end
  objects.dropCovered(clock, false)
  -- (the far tiles of the new window place come in over frames: holes are fine here, two layers are not)
  local before = bad
  local h, d = check('teleport frame ' .. f, wcx, wcy)
  if h > 0 and d == 0 then bad = before end
end
while objects.farPending() do objects.stepFar(clock, nil) end
objects.dropCovered(clock, true)
check('teleport end', wcx, wcy)
local n2, nl2 = count()
print(string.format('drive: %d frames; end %d entries (%d coarse); after the teleport %d (%d coarse); %s',
  frames, n1, nl1, n2, nl2, bad == 0 and 'OK' or (bad .. ' BAD frames')))
assert(bad == 0)
