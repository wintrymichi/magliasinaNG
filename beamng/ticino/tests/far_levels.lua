-- Outside the game: the far houses of objects.lua with their coarser levels (farbld.py LEVELS: blocks of 8, 16 and 32
-- tiles beyond the level 2 blocks, a quadtree as the far ground's) and the streamed houses of the objects queue, on a
-- made-up map. At every frame of a drive and of jumps, every tile with houses within the radius must be drawn by its
-- streamed houses or a far shape of some level (never a hole while a block splits or merges); settled: the tiles within
-- the houses' radius by their streamed houses only, the ones beyond by exactly one far shape; each level only where the
-- far ground's quadtree (split one level ahead) draws level k - 1 or k.
--   python3 tests/luajit.py tests/far_levels.lua     (pip install lupa)
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

local N, M, B = 170, 130, 4
local tiles, has, blk = {}, {}, { [2] = {}, [3] = {}, [4] = {}, [5] = {} }
for y = 0, M - 1 do
  for x = 0, N - 1 do
    if not (x > 120 and y > 80) and (x * 5 + y * 3) % 13 ~= 0 then        -- some tiles with no houses
      local k = x .. '_' .. y
      tiles[#tiles + 1] = k; has[k] = true
      for lv = 2, 5 do blk[lv][math.floor(x / 2 ^ lv) .. '_' .. math.floor(y / 2 ^ lv)] = true end
    end
  end
end
local bl, lv = {}, {}
for k in pairs(blk[2]) do bl[#bl + 1] = k end
for l = 3, 5 do
  lv[tostring(l)] = {}
  for k in pairs(blk[l]) do table.insert(lv[tostring(l)], k) end
end
local tileSet = {}
for _, k in ipairs(tiles) do tileSet[k] = true end
local cfg = { tiles = tileSet, maxRadius = HOUSES_R, origin = { 0, 0 }, cell = 256, square = 1.5, collisionRadius = 1,
              farBld = tiles, farBld2 = bl, farBld2Tiles = B, farBldL = lv, colCell = 64, farRadius = 8 }
objects.init(cfg, 'L', { addObject = function() end })
objects.FAR_BLD_HOLD_MS = 1e9
objects.FAR_BLD_RADIUS = 60
objects.LOD_D2 = 6            -- the far ground splits level k within 6 x 2^(k - 2) tiles: houses 8 / 12 / 24
local t = 0
local function clock() t = t + 1; return t end

-- what draws each tile now: streamed houses (count of its 2), far fine tile, coarse block
local CX, CY = 0, 0
local levelLive, levelD = {}, {}
local function cover()
  local real, far = {}, {}
  levelLive, levelD = {}, {}
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
          local l, bx, by = s:match('/farbld/l(%d)_(%-?%d+)_(%-?%d+)%.cdae$')
          if bx then
            local n = 2 ^ tonumber(l)
            bx, by = tonumber(bx), tonumber(by)
            levelLive[tonumber(l)] = (levelLive[tonumber(l)] or 0) + 1
            for ty = by * n, by * n + n - 1 do
              for tx = bx * n, bx * n + n - 1 do
                local k = tx .. '_' .. ty
                if has[k] then far[k] = (far[k] or 0) + 1 end
              end
            end
            local d = math.max(0, bx * n - CX, CX - (bx * n + n - 1), by * n - CY, CY - (by * n + n - 1))
            local lo, hi = levelD[tonumber(l)] or { 1e9, -1 }, nil
            levelD[tonumber(l)] = { math.min(lo[1], d), math.max(lo[2], d) }
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
  CX, CY = cx, cy
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
  if settled then
    -- level k (k >= 3) only beyond the far ground's level k - 1 split (6 x 2^(k - 3)) and within its level k one
    for l = 3, 5 do
      local r = levelD[l]
      if r then
        local lo = (l == 3) and 8 or 6 * 2 ^ (l - 3)
        local hi = (l < 5) and 6 * 2 ^ (l - 2) or 1e9
        if r[1] <= lo or r[2] > hi + 2 ^ l then
          wrong = wrong + 1
          print(string.format('  level %d drawn from %d to %d tiles (wanted beyond %d, within %d)', l, r[1], r[2], lo,
            hi + 2 ^ l))
        end
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

go('start', 40, 40, true)
for x = 41, 110 do go('drive', x, 30 + math.floor(x / 3)) end
go('jump', 120, 40, true, 1)
local s = objects.stats()
for y = 41, 80, 2 do go('drive2', 120, y) end
go('back', 118, 78)
go('jump2', 30, 70, true, 1)
local ll = {}
for l = 3, 5 do ll[#ll + 1] = string.format('l%d %d', l, levelLive[l] or 0) end
print('levels live at the end of jump2: ' .. table.concat(ll, ', '))
if not levelLive[5] or not levelLive[4] or not levelLive[3] then print('BAD a level never drawn') bad = bad + 1 end
-- the hold of the game with a queue far slower than it (Lugano after a jump: minutes): the far houses of the town stay
-- while houses are still to come (up to 547c25a they went when the hold ran out, a band of bare ground on the PC)
objects.FAR_BLD_HOLD_MS = 600
go('jump3 (short hold)', 60, 60, true, 1)
objects.FAR_BLD_HOLD_MS = 1e9
print(string.format('live %d, far houses %d fine %d coarse, %d held', s.live, s.farBld, s.farBld2, s.bldHeld))
objects.FAR_BLD_RADIUS = 0
objects.updateFar(60, 60, 57, 57, 8)
local left = 0
for _, o in pairs(objs) do if o.reg and (o.f.shapeName or ''):find('/farbld/', 1, true) then left = left + 1 end end
if left > 0 then print('BAD radius 0 left', left) bad = bad + 1 end
print(bad == 0 and 'far houses ok' or ('far houses FAILED ' .. bad), 'frames with streamed and far houses on one tile: '
  .. overlaps)
