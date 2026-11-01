-- Ticino streaming: the objects of the 384 m tiles (tiles/o_<cx>_<cy>.json, blocks.py) around the car.
-- An object is in the scene while its tile is within its radius (Chebyshev, in tiles) of the car's tile, and
-- collides only within cfg.collisionRadius: collision is rebuilt from scratch by every be:reloadCollision
-- (BeamNG.Earth, docs/research/2026-10-12-engine-limits-and-worldgen.md 1.1), so only the objects next to the car
-- may collide. An object whose collision changes is made again (a warm shape costs ~0.02-0.07 ms).
-- The far ground tiles (far/f_<cx>_<cy>.cdae) are objects too: shown outside the terrain window, within farRadius.
-- The level's own shapes do not collide with their drawn meshes: their collision is in collision cells of cfg.colCell
-- m (col/c_<i>_<j>.bin, collision.py: welded, the terrain skin and houses simplified, one piece per ground type),
-- made as ProceduralMesh pieces that are not drawn, only within cfg.colRadius of the car's cell (our TSStatic shapes
-- cost ~3 us per unique triangle in a rebuild: 1.12 M in the 3 x 3 tiles of 384 m were 3.4 s of frozen physics at
-- every tile, in-game test 2026-10-26; EarthNG measured a ProceduralMesh at 0.27 us).

-- Tried on michi's PC (2026-10-28): small street clutter never collides (NO_COLLISION_SHAPES:
-- 60 % of the colliders); the collision cells can be 64 m (cfg.colDir, cfg.colCell of stream.json:
-- a rebuild costs ~0.15 us a cell triangle, 9 cells of 128 m in Lugano were 60-110 ms); colUrgent tells a rebuild for
-- the cells from one for props or trees only (stream.lua lets those wait). COL_LAZY > 0 re-centres the cells only when
-- the car's cell is more than COL_LAZY from their centre (tried with 1: too many triangles).

local files = require('ticino/files')

local M = {}

M.NO_COLLISION_SHAPES = { 'clutter_pallet', 'clutter_metal_bin', 'clutter_big_dustbin', 'clutter_metal_drum',
  'clutter_mailboxstand', 'clutter_plastic_chair', 'clutter_metal_chair', 'clutter_round_ptable',
  'clutter_round_mtable', 'clutter_pwood_table', 'clutter_sorting_bin', 'clutter_convexmirror' }
-- DYNAMIC: a dynamic TSStatic is drawn into every sun shadow cascade at every frame (no cached shadow map); a static
-- one only when the cached map is redrawn, which an added static object asks for (~6 ms, BeamNG.Earth farfield.lua).
-- Up to 2026-10-30 every streamed object was dynamic: ~5,600 objects in Lugano drawn into every cascade each frame
-- (suspected cause of 13 fps standing still against Italy's 81, PC test pending). Static, the map is redrawn only in
-- the frames that add objects.
M.DYNAMIC = false
-- SETTLE_MS > 0 (with DYNAMIC false): objects are made dynamic and turned static together once no object was made for
-- SETTLE_MS (at most 4 x SETTLE_MS after the first), so the cached shadow map is redrawn once per batch, not in every
-- frame that adds objects. Turning dynamic -> static at runtime works (PC test 2026-10-30: 14 -> 83 fps).
M.SETTLE_MS = 0
-- the largest radius (tiles) of a group, under the build's own r: small clutter at 2 tiles (up to 960 m) was 2,609 of
-- the 5,640 objects round a dense tile, each a draw call for something a few pixels high (render CPU-bound, 2026-10-30)
M.GROUP_R = { ['props/street_life'] = 1, ['props/delineators'] = 1, ['props/shopfronts'] = 1,
              ['props/osm/furniture'] = 1, ['roads/markings'] = 2 }
M.COL_LAZY = 0             -- 1 tried: 25 cells of 128 m were 1.1 M triangles, a rebuild 170-250 ms in Lugano
M.SLOW_SPAWN_MS = 40       -- an object (or far tile) that takes longer to make is logged with its shape
M.CACHE_TILES = 400
M.FAR_SHAPE = '/levels/%s/far/f_%d_%d.cdae'
M.TILE_FILE = '/levels/%s/tiles/o_%d_%d.json'
M.COL_FILE = '/levels/%s/col/c_%d_%d.bin'
M.COL_XY_OFF_CM = 16384     -- collision.XY_OFF_CM
M.COL_HYST_M = 16          -- the car's collision cell changes only this far past its edge
M.WAVE_DEL_AT = 99         -- objects that went out of range (and only drew) are deleted after every new one is made:
                           -- at 33 m/s the deletions took their share of the bursts while 2,776 objects waited (PC
                           -- flight 2026-10-30, 1,620 live of ~3,400); was 1.5 (after the rings 0 and 1)

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
        stats = { created = 0, deleted = 0, failed = 0, tilesRead = 0 }, fresh = {} }
  S.maxR = cfg.maxRadius or 6
  S.noCol = {}                      -- groups that never collide (setCollision)
  S.farQueue, S.farPos = {}, 1
  S.has = cfg.tiles or {}
  S.farHas = {}
  for _, k in ipairs(cfg.far or {}) do S.farHas[k] = true end
  S.ftHas, S.ftLive, S.ftQueue, S.ftPos = {}, {}, {}, 1
  for _, k in ipairs(cfg.farTrees or {}) do S.ftHas[k] = true end
  S.col = { size = cfg.colCell, R = (cfg.colRadius or 1) + M.COL_LAZY, has = {}, live = {}, cell = nil, queue = {},
            types = cfg.colGroundTypes or {} }
  S.noColShape = {}
  S.shapeFile = {}
  -- the cells of 64 m (stream.json colCell; colDir if not col: the rebuild cost follows the cells' triangles)
  M.COL_FILE = '/levels/%s/' .. (cfg.colDir or 'col') .. '/c_%d_%d.bin'
  if cfg.colCell and cfg.colCell < 128 then M.COL_HYST_M = cfg.colCell / 8 end
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
  if not files.near(key) then return nil end          -- served and not there yet: asked again at refresh()
  local ok, data = pcall(jsonDecode, readFile(files.map(string.format(M.TILE_FILE, S.level, cx, cy))) or '')
  t = (ok and type(data) == 'table') and data or false
  if t then
    for _, e in ipairs(t) do
      local cap = e.g and M.GROUP_R[e.g]
      if cap and (e.r or 0) > cap then e.r = cap end
    end
  end
  S.tiles[key] = t
  S.tileOrder[#S.tileOrder + 1] = key
  S.stats.tilesRead = S.stats.tilesRead + 1
  while #S.tileOrder > M.CACHE_TILES do
    S.tiles[table.remove(S.tileOrder, 1)] = nil
  end
  return t or nil
end

-- The shape file to load: the zones' shapes are compiled to .cdae at build time (dae2cdae.py: no Collada import while
-- driving). Should a tile name a .cdae that is not installed (an older zone zip beside a newer one) the .dae is
-- taken, and a .dae with a .cdae beside it takes the .cdae. Cached by name.
local function shapeFile(name)
  local v = S.shapeFile[name]
  if v then return v end
  v = name
  if FS and type(name) == 'string' then
    local low = name:lower()
    if low:sub(-5) == '.cdae' then
      if not FS:fileExists(name) and FS:fileExists(name:sub(1, -6) .. '.dae') then v = name:sub(1, -6) .. '.dae' end
    elseif low:sub(-4) == '.dae' then
      if FS:fileExists(name:sub(1, -5) .. '.cdae') then v = name:sub(1, -5) .. '.cdae' end
    end
  end
  S.shapeFile[name] = v
  return v
end
M.shapeFile = function(name) return shapeFile(name) end

-- every live object and far tile static or dynamic (A/B test from the console: ticino_stream.setDynamic(true/false))
function M.setDynamic(on)
  M.DYNAMIC = on and true or false
  local n = 0
  local function set(id)
    local o = id and scenetree.findObjectById(id)
    if o and o:getClassName() == 'TSStatic' then o:setField('dynamic', 0, M.DYNAMIC and 'true' or 'false'); n = n + 1 end
  end
  for _, l in pairs(S.live or {}) do set(l.id) end
  for _, f in pairs(S.farLive or {}) do set(f.id) end
  return n
end

local function wantDynamic() return M.DYNAMIC or M.SETTLE_MS > 0 end
local function fresh(id)
  if M.DYNAMIC or M.SETTLE_MS <= 0 or not id then return end
  S.fresh[#S.fresh + 1] = id
end

-- the fresh dynamic objects turned static in one frame: true when it did (stream.lua calls it every frame)
function M.settle(clock)
  local f = S and S.fresh
  if not f or #f == 0 then return false end
  local t = clock()
  if #f ~= S.freshSeen then                 -- made one since the last call
    if (S.freshSeen or 0) == 0 then S.freshT0 = t end
    S.freshSeen, S.freshLast = #f, t
  end
  if t - (S.freshLast or t) < M.SETTLE_MS and t - (S.freshT0 or t) < 4 * M.SETTLE_MS then return false end
  local n = 0
  for _, id in ipairs(f) do
    local o = scenetree.findObjectById(id)
    if o then o:setField('dynamic', 0, 'false'); n = n + 1 end
  end
  S.fresh, S.freshSeen = {}, 0
  S.stats.settled = (S.stats.settled or 0) + n
  S.stats.settles = (S.stats.settles or 0) + 1
  return true, n
end

local function spawn(e, col)
  local o = createObject(e.class)
  if not o then return nil end
  for k, v in pairs(e) do
    if k == 'shapeName' then
      o:setField(k, 0, shapeFile(v))
    elseif not SKIP[k] then
      o:setField(k, 0, fieldStr(v))
    end
  end
  if e.class == 'TSStatic' then
    o:setField('collisionType', 0, col and (e.collisionType or 'Visible Mesh Final') or 'None')
    o:setField('dynamic', 0, wantDynamic() and 'true' or 'false')
  end
  o.canSave = false
  local p = e.p
  o:setPosition(vec3(p[1], p[2], p[3]))
  o:registerObject(e.name or '')
  if e.q then o:setPosRot(p[1], p[2], p[3], e.q[1], e.q[2], e.q[3], e.q[4]) end
  if e.s then o:setScale(vec3(e.s[1], e.s[2], e.s[3])) end
  S.group:addObject(o)
  if e.class == 'TSStatic' then fresh(o:getID()) end
  return o:getID()
end

local function delete(id)
  local o = scenetree.findObjectById(id)
  if o then o:delete() end
end

-- Is the shape one of NO_COLLISION_SHAPES? (cached by shape name)
local function clutter(shape)
  if not shape then return false end
  local v = S.noColShape[shape]
  if v == nil then
    v = false
    local s = string.lower(shape)
    for _, p in ipairs(M.NO_COLLISION_SHAPES) do
      if s:find(p, 1, true) then v = true; break end
    end
    S.noColShape[shape] = v
  end
  return v
end

-- Can this entry collide at all (its own collisionType, the groups switched off by setCollision, the clutter)?
local function canCollide(e)
  return e.class == 'TSStatic' and e.collisionType ~= 'None' and not S.noCol[e.g or ''] and not clutter(e.shapeName)
end

-- Distance (Chebyshev, tiles) of tile (tx, ty) from (cx, cy); nil when there is no centre yet
local clock_ = os.clock    -- the caller's ms clock (step/stepDels set it)

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
  -- the order of the wave (michi, 2026-10-29: "prima le cose vicine, poi quelle lontane a onda"): the colliders and
  -- the deletions of colliders first (physics), then the drawn objects tile ring by tile ring from the car outwards,
  -- the deletions of the objects that only drew after the rings up to WAVE_DEL_AT, the outer rings last. What was
  -- still queued for the last tile is sorted in again by its distance from the new one.
  -- An entry's place: -1 when its collision changes, WAVE_DEL_AT when it only goes, else its tile's ring
  local function prio(op)
    local e, d = op[2], dist(op[3], op[4], new)
    local want = d <= (e.r or 0)
    local c1 = want and canCollide(e) and d <= colR
    local l = S.live[op[1]]
    if (l and l.col or false) ~= c1 then return -1 end
    if not want then return M.WAVE_DEL_AT end
    return d
  end
  local q = {}
  for _, list in ipairs({ dels, cols, adds }) do
    for _, op in ipairs(list) do q[#q + 1] = op end
  end
  for i = S.qpos, #S.queue do q[#q + 1] = S.queue[i] end
  for i, op in ipairs(q) do op[5], op[6] = prio(op), i end
  table.sort(q, function(a, b)
    if a[5] ~= b[5] then return a[5] < b[5] end
    return a[6] < b[6]
  end)
  local nCol = 0
  while nCol < #q and q[nCol + 1][5] < 0 do nCol = nCol + 1 end
  local dFrom = #q + 1        -- the deletions of drawn objects are the tail of the queue (stepDels takes them from there)
  while dFrom > nCol + 1 and q[dFrom - 1][5] == M.WAVE_DEL_AT do dFrom = dFrom - 1 end
  S.queue, S.qpos = q, 1
  S.colQEnd, S.delFrom = nCol, dFrom
  S.cell = new
  return #q
end

-- Work through the queue for at most budgetMs (clock: ms function; nil: all of it, or up to the ring untilRing).
-- Each entry brings one object to what the car's tile wants NOW (an entry queued for an earlier tile may have nothing
-- left to do). Returns true when the queue is empty.
-- Bring one object to what the car's tile wants NOW (an entry queued for an earlier tile may have nothing left to do).
-- Returns true when it spawned a heavy object.
local function apply(op)
  local key, e = op[1], op[2]
  local colR = S.cfg.collisionRadius or 1
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
    local ts = clock_()
    local ok, id = pcall(spawn, e, col)
    local dts = clock_() - ts
    if dts > M.SLOW_SPAWN_MS then
      log('W', 'ticino', string.format('slow object %.0f ms: %s', dts, tostring(e.shapeName or e.class)))
    end
    if dts > (S.stats.maxSpawn or 0) then S.stats.maxSpawn, S.stats.maxShape = dts, e.shapeName or e.class end
    S.stats.spawnMs = (S.stats.spawnMs or 0) + dts
    if ok and id then
      S.live[key] = { id = id, col = col }
      if col then S.colDirty = true; S.stats.colMade = (S.stats.colMade or 0) + 1 end
      S.stats.created = S.stats.created + 1
    else
      S.stats.failed = S.stats.failed + 1
      if S.stats.failed <= 20 then log('W', 'ticino', 'object not made: ' .. tostring(e.shapeName) .. ' ' .. tostring(id)) end
    end
    return dts > M.SLOW_SPAWN_MS
  end
  return false
end

-- Work through the queue for at most budgetMs (clock: ms function; nil: all of it, or up to the ring untilRing).
-- Returns true when the queue is empty.
function M.step(clock, budgetMs, untilRing)
  clock_ = clock
  local t0 = clock()
  local q = S.queue
  while S.qpos <= #q do
    local op = q[S.qpos]
    if untilRing and (op[5] or 0) > untilRing then break end
    S.qpos = S.qpos + 1
    local heavy = apply(op)
    -- one heavy object a frame: a second one after it would add its cost to the same frame (with no budget, at a
    -- jump while the game is paused, the step goes on: it made one object of a new zone and left the rest crawling)
    if budgetMs and ((heavy and not M.BURSTING) or clock() - t0 > budgetMs) then break end
  end
  return S.qpos > #q
end

-- The deletions of drawn objects that went out of range, from the tail of the queue, for at most budgetMs: they wait
-- behind every new object (WAVE_DEL_AT), and at 33 m/s with one burst a second they never came (PC flight B
-- 2026-10-31: 10,649 live objects and 45,524 queued after 5 min). Returns the number done.
function M.stepDels(clock, budgetMs)
  clock_ = clock
  local t0, n = clock(), 0
  local q = S.queue
  while #q >= math.max(S.delFrom or #q + 1, S.qpos) do
    local op = q[#q]
    q[#q] = nil
    apply(op)
    n = n + 1
    if clock() - t0 > budgetMs then break end
  end
  return n
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
      if S.has[key] and S.tiles[key] == nil and files.ready(key) then
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
  S.colDirty, S.colUrgent = false, false
  return clock() - t0
end

-- Is the pending rebuild for the collision cells (not only props or trees, which may wait for the next one)?
function M.colUrgent() return S and S.colUrgent end

-- Collision cells: the car at (x, y). Deletes the cells beyond colRadius of its cell (with COL_HYST_M of hysteresis)
-- and queues the missing ones for stepCols. Returns true when the set changed.
function M.updateCols(x, y, force)
  local C = S.col
  if not C.size then return false end
  local cfg = S.cfg
  local i, j = math.floor((x - cfg.origin[1]) / C.size), math.floor((y - cfg.origin[2]) / C.size)
  local c = C.cell                  -- the centre of the cells made (the car's cell when they were chosen)
  if c and not force then
    local L = M.COL_LAZY
    if math.abs(i - c[1]) <= L and math.abs(j - c[2]) <= L then return false end
    local x0, y0 = cfg.origin[1] + (c[1] - L) * C.size, cfg.origin[2] + (c[2] - L) * C.size
    local span = (2 * L + 1) * C.size
    local h = M.COL_HYST_M
    if x >= x0 - h and x < x0 + span + h and y >= y0 - h and y < y0 + span + h then return false end
  end
  C.cell = { i, j }
  S.colXY = { x, y }
  local R = C.R
  local want = {}
  if R >= 0 then
    for b = j - R, j + R do
      for a = i - R, i + R do
        local k = a .. '_' .. b
        if C.has[k] and files.near(files.serving() and files.colTile(a, b, C.size) or k) then want[k] = { a, b } end
      end
    end
  end
  local changed = false
  S.colUrgent = true                -- the cells round the car changed: their rebuild is not to wait
  for k, ids in pairs(C.live) do
    if not want[k] then
      for _, id in ipairs(ids) do delete(id) end
      C.live[k] = nil
      C.tris = (C.tris or 0) - ((C.liveTris or {})[k] or 0)
      if C.liveTris then C.liveTris[k] = nil end
      changed = true
    end
  end
  -- the queue: the wanted cells not made yet, the car's own cell first; a cell half made stays where it is
  local q = {}
  if C.job and want[C.job.key] then q[1] = C.job.key
  elseif C.job then
    -- a half made cell no longer wanted: its pieces go too (they stayed in the scene before, and the cell made
    -- again later registered the same names: 56 "SimNameDictionary::insert" warnings in laptop run 3)
    for _, id in ipairs(C.job.ids) do delete(id) end
    C.tris = (C.tris or 0) - (C.job.tris or 0)
    C.job = nil
  end
  local order = {}
  for k, ab in pairs(want) do
    if not C.live[k] and not (C.job and C.job.key == k) then
      order[#order + 1] = { k, math.max(math.abs(ab[1] - i), math.abs(ab[2] - j)) }
    end
  end
  table.sort(order, function(a, b) return a[2] < b[2] end)
  for _, o in ipairs(order) do q[#q + 1] = o[1] end
  C.queue, C.want = q, want
  if #order > 0 then changed = true end
  if changed then S.colDirty = true end
  return changed
end

-- One collision piece of a cell file (collision.py: TCC1) as a ProceduralMesh, not drawn
local hasFfi, ffi = pcall(require, 'ffi')
local function colPiece(C, job)
  local s, i = job.data, job.pos
  local gt, nv, nt = s:byte(i), s:byte(i + 1) + 256 * s:byte(i + 2), s:byte(i + 3) + 256 * s:byte(i + 4)
  i = i + 5
  local off, verts, fv, faces = M.COL_XY_OFF_CM, {}, {}, {}
  local u = nil
  if hasFfi and not C.noFfi then
    -- the u16 numbers of the piece copied into a buffer (little endian, as on every PC the game runs on). Casting the
    -- Lua string itself failed in game for one cell ("arithmetic on a string value", laptop run 1, 2026-10-26):
    -- any failure here falls back to the byte path for the rest of the session.
    local okF, buf = pcall(function()
      local n = 6 * nv + 6 * nt
      local b = ffi.new('uint16_t[?]', 3 * nv + 3 * nt)
      ffi.copy(b, s:sub(i, i + n - 1), n)
      return b
    end)
    if okF then u = buf
    else
      C.noFfi = true
      log('W', 'ticino', 'collision cells: ffi decode off (' .. tostring(buf) .. '), type of data ' .. type(s))
    end
  end
  if u then
    for k = 0, nv - 1 do
      verts[k + 1] = { x = (u[3 * k] - off) * 0.01, y = (u[3 * k + 1] - off) * 0.01, z = u[3 * k + 2] * 0.01 }
      fv[k + 1] = { v = k, n = 0, u = 0 }
    end
    -- indexed, not u + 3 * nv: a uint16_t[?] array is no pointer ("bad argument #1 to '__add' (invalid C type)" for
    -- every piece in laptop run 2, so no cell had any collision)
    local w = 3 * nv
    for k = 0, nt * 3 - 1 do faces[k + 1] = fv[u[w + k] + 1] end
    i = i + 6 * nv + 6 * nt
  else
    for k = 1, nv do
      local a, b, c2, d, e, f = s:byte(i, i + 5)
      verts[k] = { x = (a + 256 * b - off) * 0.01, y = (c2 + 256 * d - off) * 0.01, z = (e + 256 * f) * 0.01 }
      fv[k] = { v = k - 1, n = 0, u = 0 }
      i = i + 6
    end
    for k = 1, nt * 3 do
      local a, b = s:byte(i, i + 1)
      faces[k] = fv[a + 256 * b + 1]
      i = i + 2
    end
  end
  job.pos = i
  local o = createObject('ProceduralMesh')
  if not o then return nil end
  job.n = job.n + 1
  o:registerObject('tc_col_' .. job.key .. '_' .. job.n)
  o.canSave = false
  S.group:addObject(o.obj or o)
  o:createMesh({ { { verts = verts, normals = { { x = 0, y = 0, z = 1 } }, uvs = { { u = 0, v = 0 } }, faces = faces,
                     material = 'tc_col_' .. string.lower(C.types[gt + 1] or 'default') } } })
  o:setPosition(vec3(job.x0, job.y0, job.z0))
  -- not drawn: collision only (EarthNG: setRenderEnabled(false) keeps the collision, setHidden drops it)
  if not pcall(function() o:setRenderEnabled(false) end) then C.noRenderOff = true end
  C.tris = (C.tris or 0) + nt         -- live triangles of the cells (made minus deleted)
  job.tris = (job.tris or 0) + nt
  return o:getID()
end

-- Make queued collision cells for at most budgetMs (nil: all); one ProceduralMesh piece at a time. A finished cell
-- marks the collision dirty. Returns true when nothing is queued any more.
function M.stepCols(clock, budgetMs)
  local C = S.col
  local t0 = clock()
  while true do
    local job = C.job
    if not job then
      local k = table.remove(C.queue or {}, 1)
      if not k then return true end
      local ab = C.want and C.want[k]
      local data = ab and readFile(files.map(string.format(M.COL_FILE, S.level, ab[1], ab[2])))
      if data and data:sub(1, 4) == 'TCC1' then
        local b1, b2, b3, b4 = data:byte(5, 8)
        local z0 = b1 + 256 * b2 + 65536 * b3 + 16777216 * b4
        if z0 >= 2147483648 then z0 = z0 - 4294967296 end
        local cfg = S.cfg
        job = { key = k, data = data, pos = 11, left = data:byte(9) + 256 * data:byte(10), n = 0, ids = {},
                x0 = cfg.origin[1] + ab[1] * C.size, y0 = cfg.origin[2] + ab[2] * C.size, z0 = z0 * 0.01 }
        C.job = job
      elseif ab then
        log('W', 'ticino', 'collision cell not readable: ' .. k)
      end
    end
    if job then
      if job.left > 0 then
        local ok, id = pcall(colPiece, C, job)
        job.left = job.left - 1
        if ok and id then job.ids[#job.ids + 1] = id
        else
          job.left = 0                 -- the read position is lost: the rest of the cell would be garbage
          C.failed = (C.failed or 0) + 1
          if C.failed <= 10 or C.failed % 100 == 0 then
            log('W', 'ticino', 'collision piece not made (' .. C.failed .. ' so far): ' .. job.key .. ' ' .. tostring(id))
          end
        end
      end
      if job.left <= 0 then
        C.live[job.key] = job.ids
        C.liveTris = C.liveTris or {}
        C.liveTris[job.key] = job.tris or 0
        C.job = nil
        S.colDirty = true
      end
    end
    if budgetMs and clock() - t0 > budgetMs then return C.job == nil and #(C.queue or {}) == 0 end
  end
end

function M.colsPending()
  local C = S and S.col
  return C and (C.job ~= nil or #(C.queue or {}) > 0) or false
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
function M.markColDirty() if S then S.colDirty = true end end
function M.colCell() return S and S.col.cell end

-- Far ground. Without far levels (stream.json farLod, farlod.py): the far tiles within farRadius of (cx, cy), deleted
-- 2 beyond it. With them (FAR_LOD): a quadtree as BeamNG.Earth's far field (farfield.lua, MIT licence): a level k tile
-- (2^k far tiles a side, k = 2..5) is split while it is within LOD_D[k] far tiles of the car's tile, a level 2 tile
-- straight into its 16 far tiles; so the far tiles reach about as far as farRadius and the coarse ones the whole map,
-- ~150 tiles a level. A tile no longer wanted stays until every wanted tile over its square is made, and the new
-- tiles over a square still covered by an old one are made hidden and shown in the frame the old one goes: never a
-- hole, never two layers drawn (dropCovered). The far tiles inside the terrain window are hidden (window origin wcx,
-- wcy in tiles, n tiles a side); the coarse ones never reach it (LOD_D[2] >= the window's reach).
M.FAR_LOD = true            -- use the far levels when the base has them
M.FARLOD_FILE = '/levels/%s/farlod/l%d_%d_%d.cdae'
M.FARLOD_INDEX = '/levels/%s/farlod/farlod.json'
M.LOD_D2 = nil              -- far tiles from the car's tile within which a level 2 tile is split (nil: farRadius - 2)
M.LOD_GROW = 2.0            -- LOD_D[k + 1] = LOD_D[k] * this (a fixed number of tiles per level's ring)
M.DROP_EVERY_MS = 100       -- how often the old tiles are checked for being covered

local function lodSetup()
  if S.lod ~= nil then return S.lod end
  S.lod = false
  if not M.FAR_LOD then return false end
  local idx = S.cfg.farLod
  if type(idx) ~= 'table' then
    local text = readFile(string.format(M.FARLOD_INDEX, S.level))
    local ok, t = pcall(jsonDecode, text or '')
    idx = ok and type(t) == 'table' and t or nil
  end
  if not idx then return false end
  local L = { has = {}, levels = {}, size = {}, D = {} }
  for ks, keys in pairs(idx) do
    local k = tonumber(ks)
    if k and k >= 2 and type(keys) == 'table' then
      L.has[k] = {}
      for _, key in ipairs(keys) do L.has[k][key] = true end
      L.levels[#L.levels + 1] = k
      L.size[k] = 2 ^ k
    end
  end
  table.sort(L.levels)
  if #L.levels == 0 or L.levels[1] ~= 2 then return false end
  for i = 2, #L.levels do if L.levels[i] ~= L.levels[i - 1] + 1 then return false end end
  L.top = L.levels[#L.levels]
  local d2 = M.LOD_D2 or math.max(7, (S.cfg.farRadius or 16) - 2)
  for _, k in ipairs(L.levels) do L.D[k] = math.floor(d2 * M.LOD_GROW ^ (k - 2) + 0.5) end
  S.lod = L
  log('I', 'ticino', string.format('far levels %d..%d: split within %d / %d / %d / %d far tiles', L.levels[1], L.top,
    L.D[2] or -1, L.D[3] or -1, L.D[4] or -1, L.D[5] or -1))
  return L
end

local function parse2(key)
  local a, b = key:match('^(%-?%d+)_(%-?%d+)$')
  return tonumber(a), tonumber(b)
end

-- the square of a far entry in far tiles: x0, y0, x1, y1 (inclusive)
local function farSquare(f)
  if f.k == 0 then return f.cx, f.cy, f.cx, f.cy end
  local s = S.lod.size[f.k]
  return f.cx * s, f.cy * s, f.cx * s + s - 1, f.cy * s + s - 1
end

local function sqDist(cx, cy, x0, y0, x1, y1)
  return math.max(math.max(0, x0 - cx, cx - x1), math.max(0, y0 - cy, cy - y1))
end

-- the wanted far entries round the car's tile: key -> { key, k, cx, cy, d } (k 0: a far tile)
local function lodWant(cx, cy)
  local L, want = S.lod, {}
  local function visit(k, i, j)
    local s = L.size[k]
    local x0, y0 = i * s, j * s
    local d = sqDist(cx, cy, x0, y0, x0 + s - 1, y0 + s - 1)
    if d <= L.D[k] then
      if k > 2 then
        local h = L.has[k - 1]
        for jj = 2 * j, 2 * j + 1 do
          for ii = 2 * i, 2 * i + 1 do
            if h[ii .. '_' .. jj] then visit(k - 1, ii, jj) end
          end
        end
      else
        for ty = y0, y0 + s - 1 do
          for tx = x0, x0 + s - 1 do
            local key = tx .. '_' .. ty
            if S.farHas[key] then
              want[key] = { key, 0, tx, ty, math.max(math.abs(tx - cx), math.abs(ty - cy)) }
            end
          end
        end
      end
    else
      local key = 'l' .. k .. '_' .. i .. '_' .. j
      want[key] = { key, k, i, j, d }
    end
  end
  for key in pairs(L.has[L.top]) do
    local i, j = parse2(key)
    visit(L.top, i, j)
  end
  return want
end

local function farApplyHidden(f)
  local h = (f.win or f.pend) and true or false
  if h ~= f.hidden then
    local o = scenetree.findObjectById(f.id)
    if o then o:setHidden(h) end
    f.hidden = h
  end
end

function M.updateFar(cx, cy, wcx, wcy, n)
  local deleted = 0
  S.farArgs = { cx, cy, wcx, wcy, n }
  S.farWin = { wcx, wcy, n }
  local want = {}
  if lodSetup() then
    want = lodWant(cx, cy)
    S.farWant = want
    S.farDoomed = {}
    for key, f in pairs(S.farLive) do
      if not want[key] then S.farDoomed[key] = f end
    end
    S.dropAt = nil
  else
    local R = S.cfg.farRadius or 16
    for key, f in pairs(S.farLive) do
      if math.max(math.abs(f.cx - cx), math.abs(f.cy - cy)) > R + 2 then
        delete(f.id)
        S.farLive[key] = nil
        deleted = deleted + 1
      end
    end
    for ty = cy - R, cy + R do
      for tx = cx - R, cx + R do
        local key = tx .. '_' .. ty
        if S.farHas[key] then want[key] = { key, 0, tx, ty, math.max(math.abs(tx - cx), math.abs(ty - cy)) } end
      end
    end
  end
  -- the missing ones, nearest first; made a few a frame by stepFar (a first-time far shape is converted by the game:
  -- making all 1,000 at once took 7.8 s at the first jump)
  local q = {}
  for key, w in pairs(want) do
    if not S.farLive[key] and (w[2] > 0 or files.far(key)) then q[#q + 1] = w end
  end
  table.sort(q, function(a, b) if a[5] ~= b[5] then return a[5] < b[5] end return a[1] < b[1] end)
  S.farQueue, S.farPos = q, 1
  for _, f in pairs(S.farLive) do M._farHide(f) end
  return deleted + M.updateFarTrees(cx, cy)
end

function M._farHide(f)
  local w = S.farWin
  if not w then return end
  if f.k == 0 then
    f.win = f.cx >= w[1] and f.cx < w[1] + w[3] and f.cy >= w[2] and f.cy < w[2] + w[3] or false
  else
    -- a coarse tile is never wanted over the window, but an old one (a jump) may still be there: hidden under the
    -- terrain, or both would be drawn
    local x0, y0, x1, y1 = farSquare(f)
    f.win = x0 < w[1] + w[3] and w[1] <= x1 and y0 < w[2] + w[3] and w[2] <= y1 or false
  end
  farApplyHidden(f)
end

-- Is every wanted entry over the square of f made (or with no file at all)?
local function covered(f)
  local want, live, L = S.farWant or {}, S.farLive, S.lod
  local x0, y0, x1, y1 = farSquare(f)
  -- a coarser wanted tile over it
  for _, k in ipairs(L.levels) do
    if k > f.k then
      local s = L.size[k]
      local key = 'l' .. k .. '_' .. math.floor(x0 / s) .. '_' .. math.floor(y0 / s)
      if want[key] then return live[key] ~= nil end
    end
  end
  -- finer wanted tiles inside it
  local function inner(k, i, j)
    if k == 0 then
      local key = i .. '_' .. j
      if want[key] and not live[key] then return false end
      return true
    end
    local key = 'l' .. k .. '_' .. i .. '_' .. j
    if want[key] then return live[key] ~= nil end
    if not L.has[k][i .. '_' .. j] then return true end
    if k > 2 then
      for jj = 2 * j, 2 * j + 1 do
        for ii = 2 * i, 2 * i + 1 do
          if not inner(k - 1, ii, jj) then return false end
        end
      end
    else
      local s = L.size[2]
      for ty = j * s, j * s + s - 1 do
        for tx = i * s, i * s + s - 1 do
          if not inner(0, tx, ty) then return false end
        end
      end
    end
    return true
  end
  if f.k == 0 then return true end      -- a far tile no coarser tile is wanted over: beyond the map's levels
  if f.k > 2 then
    for jj = 2 * f.cy, 2 * f.cy + 1 do
      for ii = 2 * f.cx, 2 * f.cx + 1 do
        if not inner(f.k - 1, ii, jj) then return false end
      end
    end
  else
    for ty = y0, y1 do
      for tx = x0, x1 do
        if not inner(0, tx, ty) then return false end
      end
    end
  end
  return true
end

local function overlaps(a, b)
  local ax0, ay0, ax1, ay1 = farSquare(a)
  local bx0, by0, bx1, by1 = farSquare(b)
  return ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1
end

-- The old far entries that are covered go, and the new ones they hid are shown, in the same frame. Returns the number
-- deleted. clock/force: at most every DROP_EVERY_MS unless force.
function M.dropCovered(clock, force)
  if not (S and S.lod and S.farDoomed) then return 0 end
  local now = clock and clock() or 0
  if not force and S.dropAt and now - S.dropAt < M.DROP_EVERY_MS then return 0 end
  S.dropAt = now
  local gone, left = {}, false
  for key, f in pairs(S.farDoomed) do
    if S.farLive[key] ~= f then S.farDoomed[key] = nil
    elseif covered(f) then gone[#gone + 1] = key
    else left = true end
  end
  for _, key in ipairs(gone) do
    local f = S.farDoomed[key]
    S.farDoomed[key] = nil
    S.farLive[key] = nil
    delete(f.id)
  end
  -- the hidden new ones that no old entry overlaps any more
  for _, f in pairs(S.farLive) do
    if f.pend then
      local still = false
      if left then
        for _, d in pairs(S.farDoomed) do
          if overlaps(f, d) then still = true; break end
        end
      end
      if not still then f.pend = nil; farApplyHidden(f) end
    end
  end
  S.stats.farDropped = (S.stats.farDropped or 0) + #gone
  return #gone
end

-- Make queued far entries for at most budgetMs; returns the number made.
function M.stepFar(clock, budgetMs)
  local t0, made = clock(), 0
  local q = S.farQueue
  while S.farPos <= #q do
    local w = q[S.farPos]
    S.farPos = S.farPos + 1
    local key, k, tx, ty = w[1], w[2], w[3], w[4]
    if not S.farLive[key] then
      local ts = clock()
      local cfg = S.cfg
      local tm = cfg.cell * cfg.square
      local s = k == 0 and 1 or S.lod.size[k]
      -- a new entry over a square an old one still covers is made hidden (shown by dropCovered)
      local f = { cx = tx, cy = ty, k = k, hidden = false, win = false }
      local pend = false
      if S.farDoomed then
        for _, d in pairs(S.farDoomed) do
          if overlaps(f, d) then pend = true; break end
        end
      end
      local o = createObject('TSStatic')
      o:setField('shapeName', 0, k == 0 and files.map(string.format(M.FAR_SHAPE, S.level, tx, ty))
        or string.format(M.FARLOD_FILE, S.level, k, tx, ty))
      o:setField('collisionType', 0, 'None')
      o:setField('decalType', 0, 'None')
      o:setField('dynamic', 0, wantDynamic() and 'true' or 'false')
      o.canSave = false
      o:setPosition(vec3(cfg.origin[1] + tx * s * tm, cfg.origin[2] + ty * s * tm, 0))
      if pend then o:setHidden(true) end
      o:registerObject('')
      S.group:addObject(o)
      fresh(o:getID())
      f.id, f.hidden, f.pend = o:getID(), pend, pend or nil
      S.farLive[key] = f
      M._farHide(f)
      made = made + 1
      local dts = clock() - ts
      if dts > M.SLOW_SPAWN_MS then log('W', 'ticino', string.format('slow far tile %.0f ms: %s', dts, key)) end
    end
    if budgetMs and clock() - t0 > budgetMs then break end
  end
  if made > 0 and S.lod then M.dropCovered(clock, S.farPos > #q) end
  if not budgetMs or clock() - t0 <= budgetMs then
    made = made + M.stepFarTrees(clock, budgetMs and math.max(0, budgetMs - (clock() - t0)) or nil)
  end
  return made
end

-- ------------------------------------------------------------------ far trees
-- The woods beyond the streamed Forest (fartrees.py: one static shape of tree clumps per 384 m tile, stream.json
-- farTrees), shown from FAR_TREES_INNER (the Forest's RADIUS, set by stream.lua) out to FAR_TREES_RADIUS tiles of the
-- car's tile (michi 2026-11-01, "non puoi anche aumentare la distanza degli alberi?"). Plain TSStatics with no
-- collision made a few a frame with the far ground: no Forest is touched, so none of the ~200 ms Forest frames.
-- A tile coming inside the Forest's rings keeps its far trees until the Forest has made it (M.forestMade, at most
-- FAR_TREES_HOLD_MS): no hole at the line where the real trees begin.
M.FAR_TREES_FILE = '/levels/%s/fartrees/t_%d_%d.cdae'
M.FAR_TREES_RADIUS = 12     -- tiles (Chebyshev) of far trees round the car's tile (settings "treeKm"); 0: none
M.FAR_TREES_INNER = 4       -- tiles that have the real Forest (stream.lua: forest.RADIUS)
M.FAR_TREES_HOLD_MS = 20000
M.forestMade = nil          -- function(key): true once the Forest shows tile key (stream.lua: forest.made)

local function cheb(key, cx, cy)
  local tx, ty = parse2(key)
  return math.max(math.abs(tx - cx), math.abs(ty - cy)), tx, ty
end

function M.updateFarTrees(cx, cy)
  if not S or not S.ftHas then return 0 end
  local R, I, n = M.FAR_TREES_RADIUS, M.FAR_TREES_INNER, 0
  S.ftCell = { cx, cy }
  for key, f in pairs(S.ftLive) do
    local d = cheb(key, cx, cy)
    if d > R + 1 or R <= I then
      delete(f.id)
      S.ftLive[key] = nil
      n = n + 1
    elseif d <= I then
      f.inner = f.inner or true          -- dropped by stepFarTrees once the Forest has the tile
    else
      f.inner, f.innerAt = nil, nil
    end
  end
  local q = {}
  if R > I then
    for ty = cy - R, cy + R do
      for tx = cx - R, cx + R do
        local key = tx .. '_' .. ty
        local d = math.max(math.abs(tx - cx), math.abs(ty - cy))
        if d > I and S.ftHas[key] and not S.ftLive[key] then q[#q + 1] = { key, d, tx, ty } end
      end
    end
  end
  table.sort(q, function(a, b) if a[2] ~= b[2] then return a[2] < b[2] end return a[1] < b[1] end)
  S.ftQueue, S.ftPos = q, 1
  return n
end

-- Make queued far-tree tiles and drop the ones the Forest has taken over, for at most budgetMs; returns the number made.
function M.stepFarTrees(clock, budgetMs)
  if not S or not S.ftHas then return 0 end
  local t0, made = clock(), 0
  M.dropFarTrees(clock)
  local q, cfg = S.ftQueue, S.cfg
  local tm = cfg.cell * cfg.square
  while S.ftPos <= #q do
    local w = q[S.ftPos]
    S.ftPos = S.ftPos + 1
    local key, tx, ty = w[1], w[3], w[4]
    if not S.ftLive[key] then
      local ts = clock()
      local o = createObject('TSStatic')
      o:setField('shapeName', 0, string.format(M.FAR_TREES_FILE, S.level, tx, ty))
      o:setField('collisionType', 0, 'None')
      o:setField('decalType', 0, 'None')
      o:setField('dynamic', 0, wantDynamic() and 'true' or 'false')
      o.canSave = false
      o:setPosition(vec3(cfg.origin[1] + tx * tm, cfg.origin[2] + ty * tm, 0))
      o:registerObject('')
      S.group:addObject(o)
      fresh(o:getID())
      S.ftLive[key] = { id = o:getID() }
      made = made + 1
      S.stats.farTrees = (S.stats.farTrees or 0) + 1
      local dts = clock() - ts
      if dts > M.SLOW_SPAWN_MS then log('W', 'ticino', string.format('slow far trees %.0f ms: %s', dts, key)) end
    end
    if budgetMs and clock() - t0 > budgetMs then break end
  end
  return made
end

-- Drop the far trees of tiles the Forest has made (looked at every 500 ms at most); returns the number dropped.
function M.dropFarTrees(clock)
  if not S or not S.ftLive then return 0 end
  local now, n = clock(), 0
  if S.ftCheckAt and now - S.ftCheckAt < 500 then return 0 end
  S.ftCheckAt = now
  for key, f in pairs(S.ftLive) do
    if f.inner then
      f.innerAt = f.innerAt or now
      if (M.forestMade and M.forestMade(key)) or now - f.innerAt > M.FAR_TREES_HOLD_MS then
        delete(f.id)
        S.ftLive[key] = nil
        n = n + 1
      end
    end
  end
  return n
end

-- Are far trees waiting for the Forest to take their tile over?
function M.farTreesHeld()
  for _, f in pairs(S and S.ftLive or {}) do if f.inner then return true end end
  return false
end

function M.farTreesPending() return S and S.ftHas and S.ftPos <= #S.ftQueue or false end

function M.hasFarLod() return S ~= nil and lodSetup() and true or false end

-- old far entries still waiting for their cover
function M.farDoomedLeft()
  if not (S and S.farDoomed) then return false end
  return next(S.farDoomed) ~= nil
end

function M.farPending() return S and (S.farPos <= #S.farQueue or M.farTreesPending()) or false end

-- The Ticino server finished tiles that were skipped (files.lua): queue what the car's tile wants of them, the
-- collision cells and the far ground again. Objects already made are left as they are.
function M.refresh(cols)
  if not S or not S.cell then return 0 end
  local c = S.cell
  S.cell = nil
  local q = M.retarget(c[1], c[2])
  if cols ~= false and S.colXY then M.updateCols(S.colXY[1], S.colXY[2], true) end
  if S.farArgs then M.updateFar(unpack(S.farArgs)) end
  return q
end

function M.refreshFar()
  if S and S.farArgs then M.updateFar(unpack(S.farArgs)) end
end

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
  for _, ids in pairs(S.col.live) do for _, id in ipairs(ids) do delete(id) end end
  if S.col.job then for _, id in ipairs(S.col.job.ids) do delete(id) end end
  S.col.live, S.col.cell, S.col.job, S.col.queue, S.col.liveTris, S.col.tris = {}, nil, nil, {}, {}, 0
  S.live, S.farLive, S.queue, S.qpos, S.delFrom = {}, {}, {}, 1, nil
  S.farQueue, S.farPos, S.farDoomed, S.farWant = {}, 1, nil, nil
end

-- A long jump: delete every streamed object at once (the far ground and the collision cells stay: updateFar and
-- updateCols handle them) and forget the queue, instead of deleting the old place's objects one queue entry at a time
-- after the new ones. Returns the number deleted.
function M.dropAll()
  if not S then return 0 end
  local n = 0
  for _, l in pairs(S.live) do delete(l.id); n = n + 1 end
  if n > 0 then S.colDirty = true end
  S.live, S.queue, S.qpos, S.colQEnd, S.cell, S.delFrom = {}, {}, 1, 0, nil, nil
  S.stats.deleted = S.stats.deleted + n
  return n
end

function M.maxRadius() return S and S.maxR or 0 end

function M.stats()
  if not S then return nil end
  local live, col = 0, 0
  for _, l in pairs(S.live) do
    live = live + 1
    if l.col then col = col + 1 end
  end
  local far, farLod, farHidden = 0, 0, 0
  for _, f in pairs(S.farLive) do
    far = far + 1
    if (f.k or 0) > 0 then farLod = farLod + 1 end
    if f.hidden then farHidden = farHidden + 1 end
  end
  local doomed = 0
  for _ in pairs(S.farDoomed or {}) do doomed = doomed + 1 end
  local cells = 0
  for _ in pairs(S.col.live) do cells = cells + 1 end
  local farTrees = 0
  for _ in pairs(S.ftLive or {}) do farTrees = farTrees + 1 end
  return { live = live, colliders = col, far = far, farLod = farLod, farHidden = farHidden, farDoomed = doomed,
           farTrees = farTrees,
           farDropped = S.stats.farDropped or 0, colCells = cells, queued = #S.queue - S.qpos + 1, created = S.stats.created,
           deleted = S.stats.deleted, failed = S.stats.failed, tilesRead = S.stats.tilesRead,
           colFailed = S.col.failed or 0, colTris = S.col.tris or 0, colFfi = hasFfi and not S.col.noFfi }
end

function M.pending() return S and S.qpos <= #S.queue end
function M.queued() return S and (#S.queue - S.qpos + 1) or 0 end
-- objects still to make (the queue without its tail of deletions)
function M.addsQueued()
  if not S then return 0 end
  return math.max(0, math.min(S.delFrom or #S.queue + 1, #S.queue + 1) - S.qpos)
end
function M.delsPending() return S and #S.queue >= math.max(S.delFrom or #S.queue + 1, S.qpos) end
-- Counters for the slow-frame log (cheap: no walk over the live objects). The slowest spawn since the last call.
function M.counts()
  if not S then return nil end
  local c = { created = S.stats.created, deleted = S.stats.deleted, colMade = S.stats.colMade or 0,
              maxSpawn = S.stats.maxSpawn or 0, maxShape = S.stats.maxShape, spawnMs = S.stats.spawnMs or 0 }
  S.stats.maxSpawn, S.stats.maxShape, S.stats.spawnMs = 0, nil, 0
  return c
end
-- Are objects of the rings up to d (tiles from the car's) still queued? (the queue is sorted by ring: the head tells)
function M.nearPending(d)
  if not S or S.qpos > #S.queue then return false end
  return (S.queue[S.qpos][5] or 0) <= d
end
-- Are colliders (and deletions) of the last retarget still queued? (they come first in the queue)
function M.collidersPending() return S and S.qpos <= (S.colQEnd or 0) end

return M
