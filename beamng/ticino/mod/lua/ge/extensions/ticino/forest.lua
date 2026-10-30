-- Ticino streaming: the forest items of the 384 m tiles (tiles/t_<cx>_<cy>.trees.json, region.py) around the car.
-- A whole region's forest is millions of items: one Forest with all of them is out of the question, so every tile
-- within RADIUS of the car's tile gets a small Forest of its own (from a pool) with its items, thinned with distance
-- (SHARE: a fixed share of the rows, the same ones every time: a move adds or removes only the difference), made and
-- removed a few hundred a frame. Only the car's tile collides (its items are of the level's own item types; the others
-- of twins with collidable 0), and a change there asks for a collision rebuild (objects.markColDirty).
-- A row: { type index into stream.json forestTypes, x, y, z, yaw (degrees, counter-clockwise from +x), scale }.
--
-- From BeamNG.Earth (c) 2026 TecnaGamer, MIT licence (github.com/TecnaGamer/BeamNG.Earth, trees.lua): a small Forest
-- per tile from a pool (one shared Forest with ~240k items made and removed slowed every tree change to ~100 ms),
-- emptied Forests never deleted (deleting one whose items were in the static collision hung the game), the twins with
-- collidable 0 (a change costs more with every colliding item), createNewItem with setFromEuler of the negated yaw.

local M = {}

M.RADIUS = 4                          -- tiles (Chebyshev) round the car's tile that get trees
M.SHARE = { [0] = 1.0, 1.0, 0.6, 0.35, 0.2 }   -- share of a tile's rows shown at that distance
M.PER_FRAME = 4000                    -- items made or removed a frame at most (a safety cap: see ONE_FOREST)
M.ONE_FOREST = true                   -- a frame finishes the pass of ONE tile and stops: a frame that touches a Forest
                                      -- costs ~185-200 ms in the engine whatever the number of items (PC 2026-10-30:
                                      -- 250 items a frame 118 slow frames, 64 a frame 110), so fewer frames, not fewer items
M.FORESTS_PER_FRAME = 1              -- Forests (tiles) a frame may change: each changed frame may redraw the cached sun
                                      -- shadow map (static scene), so a few big batches may beat many single tiles
M.BATCH_MAX_MS = 60                   -- with FORESTS_PER_FRAME > 1: the time a frame may spend on its batch
M.CHECK_EVERY = 8                     -- items between two looks at the clock (budget, ONE_FOREST off)
M.SOLID_RADIUS = 0                    -- tiles round the car's whose items collide
M.FILE = '/levels/%s/tiles/t_%d_%d.trees.json'
M.CACHE_TILES = 120
M.WAVE_NEAR = 1                       -- rings round the car's tile whose trees come whole before any farther tree
M.WAVE_PART = 0.4                     -- share of its trees a farther tile gets in the first pass of the wave

local S = nil

function M.init(cfg, level, markDirty)
  S = { cfg = cfg, level = level, has = cfg.forestTiles or {}, typeNames = cfg.forestTypes or {}, types = {},
        rows = {}, rowOrder = {}, tiles = {}, pool = {}, nForest = 0, queue = {}, qpos = 1, markDirty = markDirty,
        stats = { made = 0, removed = 0, failed = 0, missingTypes = 0 } }
end

local function rowsOf(key)
  local r = S.rows[key]
  if r ~= nil then return r or nil end
  local cx, cy = key:match('^(%-?%d+)_(%-?%d+)$')
  local ok, data = pcall(jsonDecode, readFile(string.format(M.FILE, S.level, tonumber(cx), tonumber(cy))) or '')
  r = (ok and type(data) == 'table') and data or false
  S.rows[key] = r
  S.rowOrder[#S.rowOrder + 1] = key
  while #S.rowOrder > M.CACHE_TILES do
    local old = table.remove(S.rowOrder, 1)
    if not S.tiles[old] then S.rows[old] = nil end
  end
  return r or nil
end

-- the item type of index i, solid (the level's own) or not (a twin with collidable 0)
local function itemType(i, solid)
  local key = i .. (solid and 's' or 'n')
  local d = S.types[key]
  if d ~= nil then return d or nil end
  local name = S.typeNames[i + 1]
  local base = name and scenetree.findObject(name)
  if not base then
    S.types[key] = false
    S.stats.missingTypes = S.stats.missingTypes + 1
    log('W', 'ticino', 'forest item type not found: ' .. tostring(name))
    return nil
  end
  if solid then
    S.types[key] = base
    return base
  end
  local twin = name .. '_tcn'
  d = scenetree.findObject(twin)
  if not d then
    d = (worldEditorCppApi and worldEditorCppApi.createObject) and worldEditorCppApi.createObject('TSForestItemData')
      or createObject('TSForestItemData')
    if d then
      for _, f in ipairs({ 'shapeFile', 'radius', 'mass', 'rigidity', 'tightnessCoefficient', 'dampingCoefficient',
                           'windScale', 'trunkBendScale', 'branchAmp', 'detailAmp', 'detailFreq', 'annotation' }) do
        local v = base:getField(f, 0)
        if v and v ~= '' then d:setField(f, 0, v) end
      end
      d:setField('collidable', 0, '0')
      d:registerObject(twin)
      if Sim and Sim.getDataBlockSet then Sim.getDataBlockSet():addObject(d) end
    end
  end
  S.types[key] = d or false
  return d
end

local function forestOf(t)
  local f = t.forestId and scenetree.findObjectById(t.forestId)
  while not f and #S.pool > 0 do f = scenetree.findObjectById(table.remove(S.pool)) end
  if not f then
    S.nForest = S.nForest + 1
    f = createObject('Forest')
    f.canSave = false
    f:registerObject('ticino_forest_' .. S.nForest)
    if scenetree.MissionGroup then scenetree.MissionGroup:addObject(f) end
  end
  t.forestId = f:getID()
  return f
end

-- a row is shown at share s when its fixed fraction (golden ratio of its index) is under s
local function shown(i, s)
  if s >= 1 then return true end
  local v = i * 0.6180339887
  return v - math.floor(v) < s
end

local function dist(key, c)
  local tx, ty = key:match('^(%-?%d+)_(%-?%d+)$')
  return math.max(math.abs(tonumber(tx) - c[1]), math.abs(tonumber(ty) - c[2]))
end

-- The car is in tile (cx, cy): a pass is queued for every tile whose share or solidity is to change (the queue of
-- the last move is dropped: a pass compares each row with what is made, so a half-done one leaves nothing wrong).
function M.retarget(cx, cy)
  if not S then return 0 end
  local c = { cx, cy }
  local want = {}
  for ty = cy - M.RADIUS, cy + M.RADIUS do
    for tx = cx - M.RADIUS, cx + M.RADIUS do
      local key = tx .. '_' .. ty
      if S.has[key] then
        local d = math.max(math.abs(tx - cx), math.abs(ty - cy))
        want[key] = { share = M.SHARE[d] or 0, solid = d <= M.SOLID_RADIUS }
      end
    end
  end
  for key in pairs(S.tiles) do
    if not want[key] then want[key] = { share = 0, solid = false } end
  end
  local keys = {}
  for key, w in pairs(want) do
    local t = S.tiles[key]
    if t then
      if t.dirty or t.share ~= w.share or (t.solid ~= w.solid and w.share > 0) then keys[#keys + 1] = key end
    elseif w.share > 0 then
      keys[#keys + 1] = key
    end
  end
  -- the wave (michi, 2026-10-29): the tiles up to WAVE_NEAR rings from the car get their whole share first, the
  -- farther ones then WAVE_PART of it ring by ring, then the removals and thinnings, then the rest of the far shares
  -- (a pass adds only the rows its share has over the last one: shown() is the same rows at a higher share)
  local passes = {}
  for _, key in ipairs(keys) do
    local w, t = want[key], S.tiles[key]
    local d = dist(key, c)
    local cur = t and t.share or 0
    if d <= M.WAVE_NEAR then
      passes[#passes + 1] = { key, w.share, w.solid, 0, d }
    elseif w.share <= cur then
      passes[#passes + 1] = { key, w.share, w.solid, 2, d }
    elseif M.ONE_FOREST then          -- one pass a tile: each pass is a frame that touches its Forest
      passes[#passes + 1] = { key, w.share, w.solid, 1, d }
    elseif w.share * M.WAVE_PART <= cur then
      passes[#passes + 1] = { key, w.share, w.solid, 3, d }
    else
      passes[#passes + 1] = { key, w.share * M.WAVE_PART, w.solid, 1, d }
      passes[#passes + 1] = { key, w.share, w.solid, 3, d }
    end
  end
  table.sort(passes, function(a, b)
    if a[4] ~= b[4] then return a[4] < b[4] end
    if a[5] ~= b[5] then return a[5] < b[5] end
    return a[1] < b[1]
  end)
  S.queue, S.qpos = {}, 1
  for _, p in ipairs(passes) do
    S.queue[#S.queue + 1] = { key = p[1], share = p[2], solid = p[3], pos = 1, near = p[4] == 0 }
  end
  return #S.queue
end

-- Work on the queue: at most perFrame items made or removed (nil: PER_FRAME) and budgetMs (nil: no limit).
function M.step(clock, budgetMs, perFrame)
  if not S then return true end
  local t0 = clock()
  local left = perFrame or M.PER_FRAME
  local q = S.queue
  local forests = 0
  while S.qpos <= #q do
    local op = q[S.qpos]
    local t = S.tiles[op.key]
    if not t then
      t = { share = 0, solid = op.solid, items = {}, itemSolid = {}, n = 0 }
      S.tiles[op.key] = t
    end
    local rows = rowsOf(op.key) or {}
    if op.pos == 1 then
      t.dirty = true
      if (t.solid or op.solid) and S.markDirty then S.markDirty() end
    end
    local fd
    local i = op.pos
    while i <= #rows and left > 0 do
      local want = shown(i, op.share)
      local it = t.items[i]
      if it and (not want or t.itemSolid[i] ~= op.solid) then
        fd = fd or forestOf(t):getData()
        pcall(function() fd:removeItem(it) end)
        t.items[i], t.n = nil, t.n - 1
        S.stats.removed = S.stats.removed + 1
        left = left - 1
        it = nil
      end
      if want and not it then
        local r = rows[i]
        local d = itemType(r[1], op.solid)
        if d then
          fd = fd or forestOf(t):getData()
          local m = MatrixF(true)
          m:setFromEuler(vec3(0, 0, -math.rad(r[5] or 0)))
          m:setPosition(vec3(r[2], r[3], r[4]))
          local ok, made = pcall(function() return fd:createNewItem(d, m, r[6] or 1) end)
          if ok and made then
            t.items[i], t.n = made, t.n + 1
            t.itemSolid = t.itemSolid or {}
            t.itemSolid[i] = op.solid
            S.stats.made = S.stats.made + 1
          else
            S.stats.failed = S.stats.failed + 1
          end
        end
        left = left - 1
      end
      i = i + 1
      if budgetMs and not M.ONE_FOREST and i % M.CHECK_EVERY == 0 and clock() - t0 > budgetMs then break end
    end
    op.pos = i
    if i <= #rows then return false end
    local touched = fd ~= nil
    t.share, t.solid, t.dirty = op.share, op.solid, nil
    if t.n == 0 then
      if t.forestId then S.pool[#S.pool + 1] = t.forestId end
      S.tiles[op.key] = nil
    end
    S.qpos = S.qpos + 1
    if touched then forests = forests + 1 end
    if M.ONE_FOREST and touched and budgetMs and budgetMs < 1000 and forests >= M.FORESTS_PER_FRAME then break end
    local limit = (M.FORESTS_PER_FRAME > 1 and budgetMs and budgetMs < 1000) and M.BATCH_MAX_MS or budgetMs
    if limit and clock() - t0 > limit then break end
  end
  return S.qpos > #q
end

function M.pending() return S and S.qpos <= #S.queue end
-- Are trees of the near rings (WAVE_NEAR) still queued?
function M.nearPending() return S and S.qpos <= #S.queue and S.queue[S.qpos].near or false end

-- Read (at most n) tree files of the ring just beyond RADIUS before the car gets there (a tile's JSON was read in
-- the frame its first item was made). Returns the number read.
function M.prefetch(cx, cy, n)
  if not S then return 0 end
  local R, done = M.RADIUS + 1, 0
  for ty = cy - R, cy + R do
    for tx = cx - R, cx + R do
      local key = tx .. '_' .. ty
      if S.has[key] and S.rows[key] == nil then
        rowsOf(key)
        done = done + 1
        if done >= n then return done end
      end
    end
  end
  return done
end

-- Remove every item and forget the queue (a long jump, or the end); the tiles' Forest objects go back to the pool.
-- Returns the number of items removed.
function M.clear()
  if not S then return 0 end
  local n = 0
  for _, t in pairs(S.tiles) do
    local f = t.forestId and scenetree.findObjectById(t.forestId)
    local fd = f and f:getData()
    if fd then for _, it in pairs(t.items) do pcall(function() fd:removeItem(it) end); n = n + 1 end end
    if t.forestId then S.pool[#S.pool + 1] = t.forestId end
    if t.solid and S.markDirty then S.markDirty() end
  end
  S.tiles, S.queue, S.qpos = {}, {}, 1
  S.stats.removed = S.stats.removed + n
  return n
end

function M.stats()
  if not S then return nil end
  local tiles, items = 0, 0
  for _, t in pairs(S.tiles) do tiles = tiles + 1; items = items + t.n end
  return { tiles = tiles, items = items, forests = S.nForest, queued = #S.queue - S.qpos + 1, made = S.stats.made,
           removed = S.stats.removed, failed = S.stats.failed, missingTypes = S.stats.missingTypes }
end

return M
