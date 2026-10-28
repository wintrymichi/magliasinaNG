-- Ticino streaming: the forest items of the 384 m tiles (tiles/t_<cx>_<cy>.forest.json, region.py) around the car.
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
M.PER_FRAME = 250                     -- items made or removed a frame at most
M.SOLID_RADIUS = 0                    -- tiles round the car's whose items collide
M.FILE = '/levels/%s/tiles/t_%d_%d.forest.json'
M.CACHE_TILES = 120

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
  -- removals first (they free the frame for the near tiles), then the nearest tiles
  table.sort(keys, function(a, b)
    local ra, rb = want[a].share == 0, want[b].share == 0
    if ra ~= rb then return ra end
    return dist(a, c) < dist(b, c)
  end)
  S.queue, S.qpos = {}, 1
  for _, key in ipairs(keys) do
    S.queue[#S.queue + 1] = { key = key, share = want[key].share, solid = want[key].solid, pos = 1 }
  end
  return #keys
end

-- Work on the queue: at most perFrame items made or removed (nil: PER_FRAME) and budgetMs (nil: no limit).
function M.step(clock, budgetMs, perFrame)
  if not S then return true end
  local t0 = clock()
  local left = perFrame or M.PER_FRAME
  local q = S.queue
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
      if budgetMs and i % 64 == 0 and clock() - t0 > budgetMs then break end
    end
    op.pos = i
    if i <= #rows then return false end
    t.share, t.solid, t.dirty = op.share, op.solid, nil
    if t.n == 0 then
      if t.forestId then S.pool[#S.pool + 1] = t.forestId end
      S.tiles[op.key] = nil
    end
    S.qpos = S.qpos + 1
    if budgetMs and clock() - t0 > budgetMs then break end
  end
  return S.qpos > #q
end

function M.pending() return S and S.qpos <= #S.queue end

function M.clear()
  if not S then return end
  for _, t in pairs(S.tiles) do
    local f = t.forestId and scenetree.findObjectById(t.forestId)
    local fd = f and f:getData()
    if fd then for _, it in pairs(t.items) do pcall(function() fd:removeItem(it) end) end end
  end
  S.tiles, S.queue, S.qpos = {}, {}, 1
end

function M.stats()
  if not S then return nil end
  local tiles, items = 0, 0
  for _, t in pairs(S.tiles) do tiles = tiles + 1; items = items + t.n end
  return { tiles = tiles, items = items, forests = S.nForest, queued = #S.queue - S.qpos + 1, made = S.stats.made,
           removed = S.stats.removed, failed = S.stats.failed, missingTypes = S.stats.missingTypes }
end

return M
