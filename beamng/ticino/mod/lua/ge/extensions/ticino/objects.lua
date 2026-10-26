-- Ticino streaming: the objects of the 384 m tiles (tiles/o_<cx>_<cy>.json, blocks.py) around the car.
-- An object is in the scene while its tile is within its radius (Chebyshev, in tiles) of the car's tile, and
-- collides only within cfg.collisionRadius: collision is rebuilt from scratch by every be:reloadCollision
-- (BeamNG.Earth, docs/research/2026-10-12-engine-limits-and-worldgen.md 1.1), so only the objects next to the car
-- may collide. An object whose collision changes is made again (a warm shape costs ~0.02-0.07 ms).
-- The far ground tiles (far/f_<cx>_<cy>.cdae) are objects too: shown outside the terrain window, within farRadius.
-- The level's own shapes do not collide with their drawn meshes: their collision is in collision cells of cfg.colCell
-- m (col/c_<i>_<j>.cdae, collision.py: welded, the terrain skin and houses simplified), and only the cells within
-- cfg.colRadius of the car's cell collide (a rebuild costs ~3 us per unique triangle: 1.12 M in the 3 x 3 tiles of
-- 384 m were 3.4 s of frozen physics at every tile, in-game test 2026-10-26).

local M = {}

M.CACHE_TILES = 400
M.FAR_SHAPE = '/levels/%s/far/f_%d_%d.cdae'
M.TILE_FILE = '/levels/%s/tiles/o_%d_%d.json'
M.COL_SHAPE = '/levels/%s/col/c_%d_%d.cdae'
M.COL_HYST_M = 16          -- the car's collision cell changes only this far past its edge

-- keys of an entry that are not engine fields
local SKIP = { class = true, p = true, q = true, s = true, g = true, r = true, name = true }

local function fieldStr(v)
  local t = type(v)
  if t == 'table' then
    local parts = {}
    for i, x in ipairs(v) do parts[i] = tostring(x) end
    return table.concat(parts, ' ')
  elseif t == 'boolean' then
    return v and '1' or '0'
  end
  return tostring(v)
end
M.fieldStr = fieldStr

local S = nil     -- state: cfg, level, group, tiles (cache), live, farLive, queue, stats

function M.init(cfg, level, group)
  S = { cfg = cfg, level = level, group = group, tiles = {}, tileOrder = {}, live = {}, farLive = {},
        queue = {}, qpos = 1, colDirty = false, maxR = 0,
        stats = { created = 0, deleted = 0, failed = 0, tilesRead = 0 } }
  S.maxR = cfg.maxRadius or 6
  S.noCol = {}                      -- groups that never collide (setCollision)
  S.farQueue, S.farPos = {}, 1
  S.has = cfg.tiles or {}
  S.farHas = {}
  for _, k in ipairs(cfg.far or {}) do S.farHas[k] = true end
  S.col = { size = cfg.colCell, R = cfg.colRadius or 1, has = {}, live = {}, cell = nil }
  for _, k in ipairs(cfg.colCells or {}) do S.col.has[k] = true end
end

local function tile(cx, cy)
  local key = cx .. '_' .. cy
  local t = S.tiles[key]
  if t ~= nil then return t or nil end
  if not S.has[key] then
    S.tiles[key] = false
    return nil
  end
  local ok, data = pcall(jsonDecode, readFile(string.format(M.TILE_FILE, S.level, cx, cy)) or '')
  t = (ok and type(data) == 'table') and data or false
  S.tiles[key] = t
  S.tileOrder[#S.tileOrder + 1] = key
  S.stats.tilesRead = S.stats.tilesRead + 1
  while #S.tileOrder > M.CACHE_TILES do
    S.tiles[table.remove(S.tileOrder, 1)] = nil
  end
  return t or nil
end

local function spawn(e, col)
  local o = createObject(e.class)
  if not o then return nil end
  for k, v in pairs(e) do
    if not SKIP[k] then o:setField(k, 0, fieldStr(v)) end
  end
  if e.class == 'TSStatic' then
    o:setField('collisionType', 0, col and (e.collisionType or 'Visible Mesh Final') or 'None')
    -- dynamic: an added static object redraws the sun's cached shadow map (BeamNG.Earth farfield.lua)
    o:setField('dynamic', 0, 'true')
  end
  o.canSave = false
  local p = e.p
  o:setPosition(vec3(p[1], p[2], p[3]))
  o:registerObject(e.name or '')
  if e.q then o:setPosRot(p[1], p[2], p[3], e.q[1], e.q[2], e.q[3], e.q[4]) end
  if e.s then o:setScale(vec3(e.s[1], e.s[2], e.s[3])) end
  S.group:addObject(o)
  return o:getID()
end

local function delete(id)
  local o = scenetree.findObjectById(id)
  if o then o:delete() end
end

-- Can this entry collide at all (its own collisionType, the groups switched off by setCollision)?
local function canCollide(e)
  return e.class == 'TSStatic' and e.collisionType ~= 'None' and not S.noCol[e.g or '']
end

-- Distance (Chebyshev, tiles) of tile (tx, ty) from (cx, cy); nil when there is no centre yet
local function dist(tx, ty, c)
  if not c then return math.huge end
  return math.max(math.abs(tx - c[1]), math.abs(ty - c[2]))
end

-- the radii an object of the tile can change state at (its r values and the collision radius), sorted
local function thresholds(t)
  if t.th then return t.th end
  local seen, th = { [S.cfg.collisionRadius or 1] = true }, { S.cfg.collisionRadius or 1 }
  for _, e in ipairs(t) do
    local r = e.r or 0
    if not seen[r] then seen[r] = true; th[#th + 1] = r end
  end
  table.sort(th)
  t.th = th
  return th
end

-- The car is in tile (cx, cy): queue the changes of every tile whose distance crossed one of its thresholds.
-- Returns the number of operations queued.
function M.retarget(cx, cy)
  local old, new = S.cell, { cx, cy }
  local colR = S.cfg.collisionRadius or 1
  local R = S.maxR
  local dels, cols, adds = {}, {}, {}
  local seen = {}
  local function visit(tx, ty)
    local tk = tx .. '_' .. ty
    if seen[tk] then return end
    seen[tk] = true
    local d0, d1 = dist(tx, ty, old), dist(tx, ty, new)
    if d0 == d1 or not S.has[tk] then return end
    local t = tile(tx, ty)
    if not t then return end
    local lo, hi = math.min(d0, d1), math.max(d0, d1)
    local cross = false
    for _, r in ipairs(thresholds(t)) do
      if lo <= r and r < hi then cross = true; break end
    end
    if not cross then return end
    for i, e in ipairs(t) do
      local r = e.r or 0
      local w0, w1 = d0 <= r, d1 <= r
      local c1 = w1 and canCollide(e) and d1 <= colR
      local key = tk .. '#' .. i
      local l = S.live[key]
      if not w1 then
        if l then dels[#dels + 1] = { key, e, tx, ty } end
      elseif not l then
        local op = { key, e, tx, ty }
        if c1 then cols[#cols + 1] = op else adds[#adds + 1] = op end
      elseif l.col ~= c1 then
        cols[#cols + 1] = { key, e, tx, ty }
      end
    end
  end
  for ty = cy - R, cy + R do
    for tx = cx - R, cx + R do visit(tx, ty) end
  end
  if old then
    for ty = old[2] - R, old[2] + R do
      for tx = old[1] - R, old[1] + R do visit(tx, ty) end
    end
  end
  -- deletions first, then the colliders, then everything else; what was still queued stays queued after them
  local q = {}
  for _, list in ipairs({ dels, cols, adds }) do
    for _, op in ipairs(list) do q[#q + 1] = op end
  end
  local nCol = #dels + #cols
  for i = S.qpos, #S.queue do q[#q + 1] = S.queue[i] end
  S.queue, S.qpos = q, 1
  S.colQEnd = nCol
  S.cell = new
  return #q
end

-- Work through the queue for at most budgetMs (clock: ms function; nil: all of it). Each entry brings one object
-- to what the car's tile wants NOW (an entry queued for an earlier tile may have nothing left to do).
-- Returns true when the queue is empty.
function M.step(clock, budgetMs)
  local t0 = clock()
  local q = S.queue
  local colR = S.cfg.collisionRadius or 1
  while S.qpos <= #q do
    local op = q[S.qpos]
    S.qpos = S.qpos + 1
    local key, e = op[1], op[2]
    local d = dist(op[3], op[4], S.cell)
    local want = d <= (e.r or 0)
    local col = want and canCollide(e) and d <= colR
    local l = S.live[key]
    if l and (not want or l.col ~= col) then
      delete(l.id)
      S.live[key] = nil
      S.stats.deleted = S.stats.deleted + 1
      l = nil
    end
    if want and not l then
      local ok, id = pcall(spawn, e, col)
      if ok and id then
        S.live[key] = { id = id, col = col }
        if col then S.colDirty = true end
        S.stats.created = S.stats.created + 1
      else
        S.stats.failed = S.stats.failed + 1
        if S.stats.failed <= 20 then log('W', 'ticino', 'object not made: ' .. tostring(e.shapeName) .. ' ' .. tostring(id)) end
      end
    end
    if budgetMs and clock() - t0 > budgetMs then break end
  end
  return S.qpos > #q
end

-- Read (at most n) tile files the next move may need, one ring beyond the largest radius, so that retarget finds them
-- read. Returns the number read.
function M.prefetch(n)
  local c = S.cell
  if not c then return 0 end
  local R = S.maxR + 1
  local done = 0
  for ty = c[2] - R, c[2] + R do
    for tx = c[1] - R, c[1] + R do
      local key = tx .. '_' .. ty
      if S.has[key] and S.tiles[key] == nil then
        tile(tx, ty)
        done = done + 1
        if done >= n then return done end
      end
    end
  end
  return done
end

-- Rebuild collision if a collider came or went; returns ms spent (0 when nothing to do).
function M.reloadCollisionIfDirty(clock)
  if not S.colDirty then return 0 end
  local t0 = clock()
  be:reloadCollision()
  S.colDirty = false
  return clock() - t0
end

-- Collision cells: the car at (x, y); makes and deletes the cells within colRadius of its cell (with COL_HYST_M of
-- hysteresis). Returns true when the set changed (colDirty is set: the caller rebuilds collision when it may).
function M.updateCols(x, y, force)
  local C = S.col
  if not C.size then return false end
  local cfg = S.cfg
  local i, j = math.floor((x - cfg.origin[1]) / C.size), math.floor((y - cfg.origin[2]) / C.size)
  local c = C.cell
  if c and not force then
    if c[1] == i and c[2] == j then return false end
    local x0, y0 = cfg.origin[1] + c[1] * C.size, cfg.origin[2] + c[2] * C.size
    local h = M.COL_HYST_M
    if x >= x0 - h and x < x0 + C.size + h and y >= y0 - h and y < y0 + C.size + h then return false end
  end
  C.cell = { i, j }
  local R = C.R
  local want = {}
  if R >= 0 then
    for b = j - R, j + R do
      for a = i - R, i + R do
        local k = a .. '_' .. b
        if C.has[k] then want[k] = { a, b } end
      end
    end
  end
  local changed = false
  for k, id in pairs(C.live) do
    if not want[k] then
      delete(id)
      C.live[k] = nil
      changed = true
    end
  end
  for k, ab in pairs(want) do
    if not C.live[k] then
      local o = createObject('TSStatic')
      o:setField('shapeName', 0, string.format(M.COL_SHAPE, S.level, ab[1], ab[2]))
      o:setField('collisionType', 0, 'Collision Mesh')
      o:setField('decalType', 0, 'None')
      o:setField('dynamic', 0, 'true')
      o.canSave = false
      o:setPosition(vec3(cfg.origin[1] + ab[1] * C.size, cfg.origin[2] + ab[2] * C.size, 0))
      o:registerObject('')
      S.group:addObject(o)
      C.live[k] = o:getID()
      changed = true
    end
  end
  if changed then S.colDirty = true end
  return changed
end

-- Collision cells round the car: radius in cells (-1: none), for tests.
function M.setColRadius(r)
  S.col.R = r
  local c = S.col.cell
  if not c then return false end
  local cfg = S.cfg
  return M.updateCols(cfg.origin[1] + (c[1] + 0.5) * S.col.size, cfg.origin[2] + (c[2] + 0.5) * S.col.size, true)
end

function M.colDirty() return S and S.colDirty end
function M.colCell() return S and S.col.cell end

-- Far ground: spawn the tiles within farRadius of (cx, cy) that are not there, delete the ones 2 beyond it,
-- and hide the ones inside the terrain window (window origin wcx, wcy in tiles, n tiles a side).
function M.updateFar(cx, cy, wcx, wcy, n)
  local R = S.cfg.farRadius or 16
  local deleted = 0
  for key, f in pairs(S.farLive) do
    if math.max(math.abs(f.cx - cx), math.abs(f.cy - cy)) > R + 2 then
      delete(f.id)
      S.farLive[key] = nil
      deleted = deleted + 1
    end
  end
  -- the missing tiles, nearest first; made a few a frame by stepFar (a first-time far shape is converted by the game:
  -- making all 1,000 at once took 7.8 s at the first jump)
  local want = {}
  for ty = cy - R, cy + R do
    for tx = cx - R, cx + R do
      local key = tx .. '_' .. ty
      if S.farHas[key] and not S.farLive[key] then
        want[#want + 1] = { key, tx, ty, math.max(math.abs(tx - cx), math.abs(ty - cy)) }
      end
    end
  end
  table.sort(want, function(a, b) return a[4] < b[4] end)
  S.farQueue, S.farPos = want, 1
  S.farWin = { wcx, wcy, n }
  for _, f in pairs(S.farLive) do M._farHide(f) end
  return deleted
end

function M._farHide(f)
  local w = S.farWin
  if not w then return end
  local inside = f.cx >= w[1] and f.cx < w[1] + w[3] and f.cy >= w[2] and f.cy < w[2] + w[3]
  if inside ~= f.hidden then
    local o = scenetree.findObjectById(f.id)
    if o then o:setHidden(inside) end
    f.hidden = inside
  end
end

-- Make queued far tiles for at most budgetMs; returns the number made.
function M.stepFar(clock, budgetMs)
  local t0, made = clock(), 0
  local q = S.farQueue
  while S.farPos <= #q do
    local w = q[S.farPos]
    S.farPos = S.farPos + 1
    local key, tx, ty = w[1], w[2], w[3]
    if not S.farLive[key] then
      local o = createObject('TSStatic')
      o:setField('shapeName', 0, string.format(M.FAR_SHAPE, S.level, tx, ty))
      o:setField('collisionType', 0, 'None')
      o:setField('decalType', 0, 'None')
      o:setField('dynamic', 0, 'true')
      o.canSave = false
      local cfg = S.cfg
      o:setPosition(vec3(cfg.origin[1] + tx * cfg.cell * cfg.square, cfg.origin[2] + ty * cfg.cell * cfg.square, 0))
      o:registerObject('')
      S.group:addObject(o)
      local f = { id = o:getID(), cx = tx, cy = ty, hidden = false }
      S.farLive[key] = f
      M._farHide(f)
      made = made + 1
    end
    if budgetMs and clock() - t0 > budgetMs then break end
  end
  return made
end

function M.farPending() return S and S.farPos <= #S.farQueue end

-- Collision settings at run time (tests): the collision radius in tiles and the groups that never collide. Every
-- object of the tiles around is checked again through the queue.
function M.setCollision(radius, groupsOff)
  if radius then S.cfg.collisionRadius = radius end
  S.noCol = {}
  for _, g in ipairs(groupsOff or {}) do S.noCol[g] = true end
  for _, t in pairs(S.tiles) do if t then t.th = nil end end
  local c = S.cell
  if not c then return 0 end
  S.cell = nil
  S.colDirty = true            -- a collider switched off must go from the collision too
  return M.retarget(c[1], c[2])
end

function M.clear()
  if not S then return end
  for _, l in pairs(S.live) do delete(l.id) end
  for _, f in pairs(S.farLive) do delete(f.id) end
  for _, id in pairs(S.col.live) do delete(id) end
  S.col.live, S.col.cell = {}, nil
  S.live, S.farLive, S.queue, S.qpos = {}, {}, {}, 1
  S.farQueue, S.farPos = {}, 1
end

function M.stats()
  if not S then return nil end
  local live, col = 0, 0
  for _, l in pairs(S.live) do
    live = live + 1
    if l.col then col = col + 1 end
  end
  local far = 0
  for _ in pairs(S.farLive) do far = far + 1 end
  local cells = 0
  for _ in pairs(S.col.live) do cells = cells + 1 end
  return { live = live, colliders = col, far = far, colCells = cells, queued = #S.queue - S.qpos + 1, created = S.stats.created,
           deleted = S.stats.deleted, failed = S.stats.failed, tilesRead = S.stats.tilesRead }
end

function M.pending() return S and S.qpos <= #S.queue end
-- Are colliders (and deletions) of the last retarget still queued? (they come first in the queue)
function M.collidersPending() return S and S.qpos <= (S.colQEnd or 0) end

return M
