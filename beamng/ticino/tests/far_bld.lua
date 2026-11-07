-- Outside the game: the far houses of objects.lua (farbld.py: fine tiles near, coarse blocks beyond) with the streamed
-- houses of the objects queue, on a made-up map. At every frame of a drive and of jumps, every tile with houses must be
-- drawn by its streamed houses or a far shape (never a hole while they change over: a streamed house leaving the radius
-- waits for the far houses, bldHold; a far tile inside the radius waits for the streamed houses, F.fill after a jump).
-- Settled: the tiles within the houses' radius by their streamed houses only, the ones beyond by exactly one far shape.
--   python3 tests/luajit.py tests/far_bld.lua     (pip install lupa)
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
-- the o tiles: two house shapes and a lamp each; readFile hands the path to jsonDecode, which makes the tile
function readFile(p) if p:find('/tiles/o_', 1, true) then return p end return nil end
local HOUSES_R = 6
function jsonDecode(p)
  local x, y = p:match('o_(%-?%d+)_(%-?%d+)%.json$')
  local t = {}
  for i = 1, 2 do
    t[#t + 1] = { class = 'TSStatic', g = 'buildings', r = HOUSES_R, collisionType = 'None', p = { 0, 0, 0 },
                  shapeName = string.format('/levels/L/z/bld_%s_%s_%d.cdae', x, y, i) }
  end
  t[#t + 1] = { class = 'TSStatic', g = 'props/street_lights', r = 2, p = { 0, 0, 0 },
                shapeName = string.format('/levels/L/z/lamp_%s_%s.cdae', x, y) }
  return t
end
local objects = require('ticino/objects')

local N, M, B = 140, 110, 4
local tiles, has, blk = {}, {}, {}
for y = -20, M - 1 do
  for x = -20, N - 1 do
    if not (x > 90 and y > 60) and (x * 5 + y * 3) % 13 ~= 0 then        -- some tiles with no houses
      local k = x .. '_' .. y
      tiles[#tiles + 1] = k; has[k] = true
      blk[math.floor(x / B) .. '_' .. math.floor(y / B)] = true
    end
  end
end
local bl = {}
for k in pairs(blk) do bl[#bl + 1] = k end
local tileSet = {}
for _, k in ipairs(tiles) do tileSet[k] = true end
local cfg = { tiles = tileSet, maxRadius = HOUSES_R, origin = { 0, 0 }, cell = 256, square = 1.5, collisionRadius = 1,
              farBld = tiles, farBld2 = bl, farBld2Tiles = B, colCell = 64 }
objects.init(cfg, 'L', { addObject = function() end })
objects.FAR_BLD_HOLD_MS = 1e9
local t = 0
local function clock() t = t + 1; return t end

-- what draws each tile now: streamed houses (count of its 2), far fine tile, coarse block
local function cover()
  local real, far = {}, {}
  for _, o in pairs(objs) do
    if o.reg and not o.hidden then
      local s = o.f.shapeName or ''
      local x, y = s:match('/bld_(%-?%d+)_(%-?%d+)_%d%.cdae$')
      if x then
        local k = x .. '_' .. y
        real[k] = (real[k] or 0) + 1
      else
        x, y = s:match('/farbld/b_(%-?%d+)_(%-?%d+)%.cdae$')
        if x then
          local k = x .. '_' .. y
          far[k] = (far[k] or 0) + 1
        else
          local bx, by = s:match('/farbld/l2_(%-?%d+)_(%-?%d+)%.cdae$')
          if bx then
            bx, by = tonumber(bx), tonumber(by)
            for ty = by * B, by * B + B - 1 do
              for tx = bx * B, bx * B + B - 1 do
                local k = tx .. '_' .. ty
                if has[k] then far[k] = (far[k] or 0) + 1 end
              end
            end
          end
        end
      end
    end
  end
  return real, far
end

local bad, overlaps = 0, 0
local before = {}
local function check(what, cx, cy, settled)
  local real, far = cover()
  local R, I = objects.FAR_BLD_RADIUS, objects.FAR_BLD_INNER
  local holes, two, wrong = 0, 0, 0
  for k in pairs(has) do
    local x, y = k:match('^(%-?%d+)_(%-?%d+)$')
    local d = math.max(math.abs(tonumber(x) - cx), math.abs(tonumber(y) - cy))
    local r, f = real[k] or 0, far[k] or 0
    local drawn = r == 2 or f > 0
    if before[k] and not drawn and d <= R then
      holes = holes + 1
      if os.getenv('WHY') then print('  hole', k, 'd', d, 'real', r, 'far', f) end
    end
    if r > 0 and f > 0 then two = two + 1 end
    if settled then
      if d <= I and (r ~= 2 or f > 0) then wrong = wrong + 1 end
      if d > I and d <= R and (r > 0 or f ~= 1) then
        wrong = wrong + 1
        if os.getenv('WHY') then print('  wrong', k, 'd', d, 'real', r, 'far', f) end
      end
    end
  end
  if holes > 0 or wrong > 0 then
    bad = bad + 1
    print(string.format('BAD %s at %d,%d: %d holes, %d wrong when settled', what, cx, cy, holes, wrong))
  end
  if two > 0 then overlaps = overlaps + 1 end
  if settled then
    before = {}
    for k in pairs(has) do
      if (real[k] or 0) == 2 or (far[k] or 0) > 0 then before[k] = true end
    end
  end
end

-- a move as stream.lua makes it: retarget (+ far again), then frames of queue work; jumps drop everything first
local function go(what, cx, cy, jump, perFrame)
  if jump then objects.dropAll(); before = {} end      -- (a jump removes the old place's houses at once, by design)
  objects.retarget(cx, cy)
  objects.updateFar(cx, cy, cx - 3, cy - 3, 8)
  local frames, allDrawn, allReal, lost = 0, nil, nil, 0
  while objects.pending() or objects.farPending() or objects.farBldHeld() do
    objects.step(clock, perFrame or 3)
    objects.stepDels(clock, 2)
    objects.stepFar(clock, 3)
    objects.dropFarBld(clock)
    frames = frames + 1
    check(what, cx, cy, false)
    if jump and not allReal then
      -- the town round the car after a jump: drawn by far houses (F.fill) long before every streamed house is made
      local real, far = cover()
      local drawn, made = true, true
      for k in pairs(has) do
        local x, y = k:match('^(%-?%d+)_(%-?%d+)$')
        if math.max(math.abs(tonumber(x) - cx), math.abs(tonumber(y) - cy)) <= objects.FAR_BLD_INNER then
          if (real[k] or 0) < 2 then made = false end
          if (real[k] or 0) < 2 and (far[k] or 0) == 0 then drawn = false end
        end
      end
      if drawn and not allDrawn then allDrawn = frames end
      if allDrawn and not drawn then lost = lost + 1 end   -- drawn once, then a hole again before its houses came
      if made then allReal = frames end
    end
    if frames > 20000 then print('BAD stuck', what) bad = bad + 1 break end
  end
  check(what .. ' settled', cx, cy, true)
  if jump then
    print(string.format('%s: the houses round the car drawn after %s frames, all streamed after %s, %d frames with a '
      .. 'hole between', what, tostring(allDrawn), tostring(allReal), lost))
    if not allDrawn or not allReal or allDrawn >= allReal or lost > 0 then print('BAD no fill', what) bad = bad + 1 end
  end
  return frames
end

go('start', 20, 26, true)
for x = 21, 60 do go('drive', x, 20 + math.floor(x / 3)) end
go('jump', 100, 30, true, 1)
local s = objects.stats()
for y = 31, 50 do go('drive2', 100, y) end
go('back', 98, 48)
go('jump2', 30, 70, true, 1)
-- the hold of the game with a queue far slower than it (Lugano after a jump: minutes): the far houses of the town stay
-- while houses are still to come (up to 547c25a they went when the hold ran out, a band of bare ground on the PC)
objects.FAR_BLD_HOLD_MS = 600
go('jump3 (short hold)', 60, 40, true, 1)
objects.FAR_BLD_HOLD_MS = 1e9
print(string.format('live %d, far houses %d fine %d coarse, %d held', s.live, s.farBld, s.farBld2, s.bldHeld))
objects.FAR_BLD_RADIUS = 0
objects.updateFar(30, 70, 27, 67, 8)
local left = 0
for _, o in pairs(objs) do if o.reg and (o.f.shapeName or ''):find('/farbld/', 1, true) then left = left + 1 end end
if left > 0 then print('BAD radius 0 left', left) bad = bad + 1 end
print(bad == 0 and 'far houses ok' or ('far houses FAILED ' .. bad), 'frames with streamed and far houses on one tile: '
  .. overlaps)
