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

local files = require('ticino/files')

local M = {}

M.RADIUS = 4                          -- tiles (Chebyshev) round the car's tile that get trees
M.SHARE = { [0] = 1.0, 1.0, 1.0, 0.25, 0.25 }  -- share of a tile's rows shown at that distance. Was 1/1/0.6/0.35/0.2:
                                      -- ring 2 whole means no pass when a tile comes into ring 1 (the "near" frames of
                                      -- the PC flight, ~200 ms each), rings 3 and 4 alike one pass fewer on the way in;
                                      -- with HYST about 30 % fewer passes a tile crossed, ~35 % more trees live
M.HYST = 1                            -- a tile keeps its share (and its collision) until it is this many rings beyond
                                      -- the ring that share belongs to: no pass on the way out for every ring crossed
                                      -- (PC flight 2026-10-30: 141 tiles queued at 33 m/s, each pass a ~200 ms frame)
M.PER_FRAME = 4000                    -- items made or removed a frame at most (a safety cap: see ONE_FOREST)
M.ONE_FOREST = true                   -- a frame finishes the pass of ONE tile and stops: a frame that touches a Forest
                                      -- costs ~185-200 ms in the engine whatever the number of items (PC 2026-10-30:
                                      -- 250 items a frame 118 slow frames, 64 a frame 110), so fewer frames, not fewer items
M.FORESTS_PER_FRAME = 1              -- Forests (tiles) a frame may change: each changed frame may redraw the cached sun
                                      -- shadow map (static scene), so a few big batches may beat many single tiles
M.BATCH_MAX_MS = 60                   -- with FORESTS_PER_FRAME > 1: the time a frame may spend on its batch
M.BLOCK = 3                           -- tiles of a BLOCK x BLOCK square share one Forest, and a frame does the passes
                                      -- of all of them at once: a frame that touches a Forest costs ~185-230 ms whatever
                                      -- it adds (PC flight 2026-10-31: +140 items 185 ms, +1,305 228 ms), so fewer
                                      -- Forests touched, fewer such frames (emulated: 31 a tile crossed with 1, 18 with 2,
                                      -- 11 with 3). PC flight 2026-10-31: near-forest frames 63 -> 7 (2) -> 3 (3),
                                      -- frames over 100 ms 130 -> 70 -> 52, 80.5 -> 83.0 fps; a Forest of ~3,000
                                      -- items still costs ~250 ms a touch, so its size adds little.
M.PASS_MAX_MS = 30                    -- Lua ms of a frame's forest work at most (budgeted calls; 0: no cap)
M.CHECK_EVERY = 8                     -- items between two looks at the clock (budget, ONE_FOREST off)
M.SOLID_RADIUS = 0                    -- tiles round the car's whose items collide
M.FILE = '/levels/%s/tiles/t_%d_%d.trees.json'
M.CACHE_TILES = 200                   -- (120 was under RADIUS 4 + the prefetched ring: 81 + 40)
M.WAVE_NEAR = 1                       -- rings round the car's tile whose trees come whole before any farther tree
M.WAVE_PART = 0.4                     -- share of its trees a farther tile gets in the first pass of the wave
-- Shape variants (BeamNG.Earth trees.lua SHAPE_VARIANTS, 2026-10-15 probes): a frame that adds or removes Forest items
-- costs the engine ~0.5 us for EVERY item in the level of each SHAPE it touches, whatever its Forest: the "~200 ms a
-- touch whatever it adds" of our PC flights (a pass touches nearly all 43 tree shapes, whose items add up to ~400k).
-- The engine tells shapes apart by their path, so the non-colliding items of a block use one of SHAPE_VARIANTS
-- spellings of each path ('dir/./name', 'dir/././name': the same file, a shape of its own): a pass then touches
-- about 1/SHAPE_VARIANTS of the population. A variant's first items cost one load (~12 ms) and its own copy of the
-- shape in memory. 1 = off (as built); 4 = Earth's value, to be checked on the PC (frames, and no imposter squares).
M.SHAPE_VARIANTS = 1

-- Forests made while the level loads, for the pool: the near-forest frames of 186-196 ms (4 a flight, PC 2026-11-01,
-- 4a53bd1) came about one per new 3x3 block early in a flight, when the pool was still empty and each new block
-- created and registered a Forest in that frame. The step's timing (read, parse, new Forest, items) is in the
-- slow-frame line to tell.
M.POOL_WARM = 24

local S = nil

local function newForest()
  S.nForest = S.nForest + 1
  local f = createObject('Forest')
  f.canSave = false
  f:registerObject('ticino_forest_' .. S.nForest)
  if scenetree.MissionGroup then scenetree.MissionGroup:addObject(f) end
  return f
end

function M.init(cfg, level, markDirty)
  S = { cfg = cfg, level = level, has = cfg.forestTiles or {}, typeNames = cfg.forestTypes or {}, types = {},
        rows = {}, rowOrder = {}, tiles = {}, pool = {}, nForest = 0, blocks = {}, fn = {}, queue = {}, qpos = 1, markDirty = markDirty,
        stats = { made = 0, removed = 0, failed = 0, missingTypes = 0 } }
  for _ = 1, M.POOL_WARM do S.pool[#S.pool + 1] = newForest():getID() end
end

-- A tile's rows ([[type, x, y, z, yaw, scale], ...]) are parsed here, a slice at a time, not by jsonDecode: one
-- decode of a 100-300 kB tile took ~170 ms of Lua in one frame (PC 2026-11-01: "near forest" frames of 185-205 ms
-- that added 7 trees). M.PARSE_MS of parsing a frame at most when budgeted; whole while paused.
M.PARSE_MS = 6
local function remember(key, r)
  S.rows[key] = r
  S.rowOrder[#S.rowOrder + 1] = key
  while #S.rowOrder > M.CACHE_TILES do
    local old = table.remove(S.rowOrder, 1)
    if not S.tiles[old] then S.rows[old] = nil end
  end
end

-- Parse tile key's rows for at most budgetMs (nil: all); returns the rows when done, nil while not.
local function parseRows(key, clock, budgetMs)
  local r = S.rows[key]
  if r ~= nil then return r or nil end
  local ps = S.parsing
  if not ps or ps.key ~= key then
    local cx, cy = key:match('^(%-?%d+)_(%-?%d+)$')
    local t0 = clock and clock()
    local txt = readFile(files.map(string.format(M.FILE, S.level, tonumber(cx), tonumber(cy))))
    if type(txt) ~= 'string' then remember(key, false); return nil end
    ps = { key = key, txt = txt, pos = 1, rows = {}, ms = t0 and (clock() - t0) or 0 }
    S.parsing = ps
  end
  local txt, rows, find, sub, tonum = ps.txt, ps.rows, string.find, string.sub, tonumber
  local t0 = clock and clock()
  local p, n = ps.pos, #rows
  while true do
    local a, b = find(txt, '%[[^%[%]]*%]', p)
    if not a then break end
    local row, k = {}, 0
    local q = a + 1
    while q < b do
      local c = find(txt, ',', q, true)
      if not c or c > b then c = b end
      k = k + 1
      row[k] = tonum(sub(txt, q, c - 1))
      q = c + 1
    end
    n = n + 1
    rows[n] = row
    p = b + 1
    if budgetMs and n % 64 == 0 and clock() - t0 > budgetMs then
      ps.pos = p
      ps.ms = ps.ms + clock() - t0
      return nil
    end
  end
  S.parsing = nil
  S.stats.parsed = (S.stats.parsed or 0) + 1
  S.stats.parseMs = (S.stats.parseMs or 0) + ps.ms + (t0 and clock() - t0 or 0)
  remember(key, rows)
  return rows
end
M.parseRows = function(key, clock, budgetMs) return S and parseRows(key, clock, budgetMs) end

-- 'dir/name.dae' spelled 'dir/./name.dae' (v = 1), 'dir/././name.dae' (v = 2), ...
local function variantPath(p, v)
  if v <= 0 or type(p) ~= 'string' then return p end
  local dir, name = p:match('^(.*)/([^/]+)$')
  if not dir then return p end
  return dir .. string.rep('/.', v) .. '/' .. name
end

-- the variant of a tile's (block's) non-colliding items: fixed by its block key
local function variantOf(key)
  local V = M.SHAPE_VARIANTS or 1
  if V <= 1 then return 0 end
  local tx, ty = key:match('^(%-?%d+)_(%-?%d+)$')
  tx, ty = tonumber(tx), tonumber(ty)
  if M.BLOCK > 1 then tx, ty = math.floor(tx / M.BLOCK), math.floor(ty / M.BLOCK) end
  return (tx * 7 + ty * 13) % V            -- neighbouring blocks differ
end

-- the item type of index i, solid (the level's own) or not (a twin with collidable 0; variant v > 0: its shape path
-- spelled another way, SHAPE_VARIANTS)
local function itemType(i, solid, v)
  v = (not solid and v) or 0
  local key = i .. (solid and 's' or 'n') .. (v > 0 and v or '')
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
  local twin = name .. '_tcn' .. (v > 0 and ('_v' .. v) or '')
  d = scenetree.findObject(twin)
  if not d then
    d = (worldEditorCppApi and worldEditorCppApi.createObject) and worldEditorCppApi.createObject('TSForestItemData')
      or createObject('TSForestItemData')
    if d then
      for _, f in ipairs({ 'shapeFile', 'radius', 'mass', 'rigidity', 'tightnessCoefficient', 'dampingCoefficient',
                           'windScale', 'trunkBendScale', 'branchAmp', 'detailAmp', 'detailFreq', 'annotation' }) do
        local val = base:getField(f, 0)
        if f == 'shapeFile' then val = variantPath(val, v) end
        if val and val ~= '' then d:setField(f, 0, val) end
      end
      d:setField('collidable', 0, '0')
      d:registerObject(twin)
      if Sim and Sim.getDataBlockSet then Sim.getDataBlockSet():addObject(d) end
    end
  end
  S.types[key] = d or false
  return d
end

local function blockOf(key)
  if M.BLOCK <= 1 then return nil end
  local tx, ty = key:match('^(%-?%d+)_(%-?%d+)$')
  return math.floor(tonumber(tx) / M.BLOCK) .. '_' .. math.floor(tonumber(ty) / M.BLOCK)
end

local function forestOf(t, key)
  local bk = not t.forestId and blockOf(key)
  local b = bk and S.blocks[bk]
  if b then t.forestId, t.block = b.id, bk; b.tiles = b.tiles + 1 end
  local f = t.forestId and scenetree.findObjectById(t.forestId)
  while not f and #S.pool > 0 do f = scenetree.findObjectById(table.remove(S.pool)) end
  if not f then
    local clk = S.clk or function() return os.clock() * 1000 end
    local t0 = clk()
    f = newForest()
    S.stats.newForests = (S.stats.newForests or 0) + 1
    if S.tm then S.tm.new = S.tm.new + clk() - t0 end
  end
  t.forestId = f:getID()
  if bk and not b then S.blocks[bk] = { id = t.forestId, tiles = 1 }; t.block = bk end
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
      if S.has[key] and files.near(key) then
        local d = math.max(math.abs(tx - cx), math.abs(ty - cy))
        want[key] = { share = M.SHARE[d] or 0, solid = d <= M.SOLID_RADIUS }
      end
    end
  end
  for key in pairs(S.tiles) do
    if not want[key] then want[key] = { share = 0, solid = false } end
  end
  local keys = {}
  -- hysteresis: a tile already at a share it would have HYST rings closer keeps it (and its collision while within
  -- SOLID_RADIUS + HYST); only a higher share, a tile that must collide now, or one beyond that is passed again
  for key, w in pairs(want) do
    local t = S.tiles[key]
    if t and not t.dirty and M.HYST > 0 then
      local d = dist(key, c)
      local keep = M.SHARE[math.max(0, d - M.HYST)] or 0
      if w.share < t.share and t.share <= keep then w.share = t.share end
      if t.solid and not w.solid and d <= M.SOLID_RADIUS + M.HYST then w.solid = true end
    end
  end
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
  if M.BLOCK > 1 then             -- the passes of one block's tiles next to each other (same class): one frame for them
    local out, done = {}, {}
    for i, p in ipairs(passes) do
      if not done[i] then
        local bk = blockOf(p[1])
        for j = i, #passes do
          local o = passes[j]
          if not done[j] and o[4] == p[4] and blockOf(o[1]) == bk then out[#out + 1] = o; done[j] = true end
        end
      end
    end
    passes = out
  end
  S.queue, S.qpos = {}, 1
  for _, p in ipairs(passes) do
    S.queue[#S.queue + 1] = { key = p[1], share = p[2], solid = p[3], pos = 1, near = p[4] == 0 }
  end
  return #S.queue
end

-- Work on the queue: at most perFrame items made or removed (nil: PER_FRAME) and budgetMs (nil: no limit).
function M.step(clock, budgetMs, perFrame, burstMs)
  if not S then return true end
  local t0 = clock()
  local passCap = M.PASS_MAX_MS > 0 and ((budgetMs and budgetMs < 1000) or burstMs) and M.PASS_MAX_MS or nil
  local left = perFrame or M.PER_FRAME
  local q = S.queue
  local forests, ids = 0, {}
  S.tm, S.clk = { parse = 0, new = 0, slowest = 0 }, clock
  while S.qpos <= #q do
    local op = q[S.qpos]
    local t = S.tiles[op.key]
    if not t then
      t = { share = 0, solid = op.solid, items = {}, itemSolid = {}, n = 0 }
      S.tiles[op.key] = t
    end
    local rows = S.rows[op.key]
    if rows == nil then
      -- the tile's rows not parsed yet: parse them for at most PARSE_MS (whole when unbudgeted, i.e. paused), and if
      -- they are not done, this frame does nothing more
      local cap = (passCap or (budgetMs and budgetMs < 1000)) and M.PARSE_MS or nil
      if cap and clock() - t0 > 1 then return false end   -- a pass already ran in this frame: parse in the next
      local tp = clock()
      rows = parseRows(op.key, clock, cap)
      S.tm.parse = S.tm.parse + clock() - tp
      if rows == nil and S.rows[op.key] == nil then return false end
    end
    rows = rows or {}
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
        fd = fd or forestOf(t, op.key):getData()
        pcall(function() fd:removeItem(it) end)
        t.items[i], t.n = nil, t.n - 1
        S.fn[t.forestId] = (S.fn[t.forestId] or 1) - 1
        S.stats.removed = S.stats.removed + 1
        left = left - 1
        it = nil
      end
      if want and not it then
        local r = rows[i]
        local d = itemType(r[1], op.solid, variantOf(op.key))
        if d then
          fd = fd or forestOf(t, op.key):getData()
          local m = MatrixF(true)
          m:setFromEuler(vec3(0, 0, -math.rad(r[5] or 0)))
          m:setPosition(vec3(r[2], r[3], r[4]))
          local tc = clock()
          local ok, made = pcall(function() return fd:createNewItem(d, m, r[6] or 1) end)
          tc = clock() - tc
          if tc > S.tm.slowest then S.tm.slowest = tc end
          if ok and made then
            t.items[i], t.n = made, t.n + 1
            S.fn[t.forestId] = (S.fn[t.forestId] or 0) + 1
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
      -- a pass split over frames when the Lua of one frame passes PASS_MAX_MS (createNewItem ~70 us a tree: a whole
      -- near tile of 2,400-4,000 trees was 195-270 ms of streamer Lua in one frame, PC 2026-11-01); not while paused
      if passCap and i % M.CHECK_EVERY == 0 and clock() - t0 > passCap then break end
    end
    op.pos = i
    if i <= #rows then return false end
    local touched = fd ~= nil
    t.share, t.solid, t.dirty = op.share, op.solid, nil
    local fid = t.forestId
    if t.n == 0 then
      local b = t.block and S.blocks[t.block]
      if b then
        b.tiles = b.tiles - 1
        if b.tiles <= 0 then S.pool[#S.pool + 1] = b.id; S.blocks[t.block] = nil end
      elseif t.forestId then
        S.pool[#S.pool + 1] = t.forestId
      end
      S.tiles[op.key] = nil
    end
    S.qpos = S.qpos + 1
    if touched and not ids[fid] then
      ids[fid] = true
      forests = forests + 1
      S.stats.touched = (S.stats.touched or 0) + 1
    end
    if touched then
      S.stats.lastKey = string.format('%s, %d in its Forest; step %.0f ms: parse %.0f, new Forest %.0f, slowest item %.1f',
        op.key, S.fn[fid] or 0, clock() - t0, S.tm.parse, S.tm.new, S.tm.slowest)
    end
    -- the next pass in the queue on the same Forest (a block) goes in this frame too: it costs the frame little more
    local nx = q[S.qpos]
    local same = nx and fid and S.tiles[nx.key] and S.tiles[nx.key].forestId == fid
    if not same and nx and fid and M.BLOCK > 1 and not (S.tiles[nx.key] and S.tiles[nx.key].forestId) then
      local b = S.blocks[blockOf(nx.key) or '']
      same = b and b.id == fid
    end
    if M.ONE_FOREST and touched and not same and budgetMs and budgetMs < 1000 and forests >= M.FORESTS_PER_FRAME then break end
    if same and passCap and clock() - t0 > passCap then break end   -- the rest of the block in the next frame
    if same then
      -- (no time limit between the passes of one block: a second frame on the same Forest costs as much again)
    elseif burstMs then
      if clock() - t0 > burstMs then break end
    else
      local limit = (M.FORESTS_PER_FRAME > 1 and budgetMs and budgetMs < 1000) and M.BATCH_MAX_MS or budgetMs
      if limit and clock() - t0 > limit then break end
    end
  end
  return S.qpos > #q
end

function M.pending() return S and S.qpos <= #S.queue end

-- Does the Forest show tile key (made, no pass of it left in the queue)? (objects.lua: far trees drop then)
function M.made(key)
  local t = S and S.tiles[key]
  if not t or (t.share or 0) <= 0 then return false end
  for i = S.qpos, #S.queue do
    if S.queue[i].key == key then return false end
  end
  return true
end
-- Counters for the slow-frame log
function M.counts()
  if not S then return nil end
  return { made = S.stats.made, removed = S.stats.removed, touched = S.stats.touched or 0, lastKey = S.stats.lastKey }
end
-- Are trees of the near rings (WAVE_NEAR) still queued?
function M.nearPending() return S and S.qpos <= #S.queue and S.queue[S.qpos].near or false end

-- Read (at most n) tree files of the ring just beyond RADIUS before the car gets there (a tile's JSON was read in
-- the frame its first item was made). Returns the number read.
function M.prefetch(cx, cy, n, clock, budgetMs)
  if not S then return 0 end
  budgetMs = budgetMs or M.PARSE_MS
  -- a tile being parsed first, then the tiles of the queue, then the ring just beyond RADIUS
  if S.parsing then
    parseRows(S.parsing.key, clock, clock and budgetMs or nil)
    return 1
  end
  for j = S.qpos, #S.queue do
    local key = S.queue[j].key
    if S.rows[key] == nil and files.ready(key) then
      parseRows(key, clock, clock and budgetMs or nil)
      return 1
    end
  end
  local R, done = M.RADIUS + 1, 0
  for ty = cy - R, cy + R do
    for tx = cx - R, cx + R do
      local key = tx .. '_' .. ty
      if S.has[key] and S.rows[key] == nil and files.ready(key) then
        parseRows(key, clock, clock and budgetMs or nil)
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
  local n, seen = 0, {}
  for _, t in pairs(S.tiles) do
    local f = t.forestId and scenetree.findObjectById(t.forestId)
    local fd = f and f:getData()
    if fd then for _, it in pairs(t.items) do pcall(function() fd:removeItem(it) end); n = n + 1 end end
    if t.forestId and not seen[t.forestId] then seen[t.forestId] = true; S.pool[#S.pool + 1] = t.forestId end
    if t.solid and S.markDirty then S.markDirty() end
  end
  S.tiles, S.queue, S.qpos, S.blocks, S.fn = {}, {}, 1, {}, {}
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

-- for tests
M._variantPath, M._variantOf = variantPath, variantOf

return M
