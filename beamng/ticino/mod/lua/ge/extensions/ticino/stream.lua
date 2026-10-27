-- Ticino streaming (GE extension 'ticino_stream'): one TerrainBlock of 2048 x 2048 samples that follows the car,
-- put together from the zone's blocks, and the objects of the 384 m tiles around it (beamng/ticino/README.md).
-- Active only in the level 'ticino'.
--
-- The terrain window moves by whole tiles (cfg.cell samples, 384 m) so that the car's tile stays the 4th or 5th of
-- its 8: the car is always at least 3 tiles (1,152 m) from its edge. The next window is written to /temp/ticino/
-- over several frames (a coroutine, BUDGET_MS a frame: terwin.lua, png.lua) and then swapped in, in one frame, by
-- terrainFile + postApply with a new file name each time (BeamNG.Earth's .ter swap, 92 ms for 2048^2 there; collision
-- follows by the next frame with no reloadCollision: terrain.lua M.swap, docs/research/2026-10-12 section 7).
-- A spawn, a teleport or a car more than a tile out of the window is a "jump": the game is paused, the window and the
-- objects next to the car are made at once, and the game goes on two frames later.
--
-- Parts of this design and of the engine calls come from BeamNG.Earth (c) 2026 TecnaGamer, MIT licence
-- (github.com/TecnaGamer/BeamNG.Earth): terrain.lua (the .ter swap, base colour fields), groundcover.lua
-- (flushGroundCoverGrids after a block change), farfield.lua (runtime TSStatic, setPosRot's quaternion), simhold.lua.
--
-- Console:
--   ticino_stream.status()            what is loaded, the last moves' timings
--   ticino_stream.setFocus(x, y)      stream around (x, y) instead of the car (nil: back to the car); for tests
--   ticino_stream.followCamera(true)  stream around the camera (free camera flights)
--   ticino_stream.dropAIRoads()       delete the AI DecalRoads once the AI map is built (each re-clips on every
--                                     terrain change: to measure)
-- Every move is logged to <user folder>/ticino_perf.csv.

local terwin = require('ticino/terwin')
local objects = require('ticino/objects')

local M = {}

M.LEVEL = 'ticino'
M.BUDGET_MS = 4            -- Lua time a frame for the next window's files
M.OBJ_BUDGET_MS = 3        -- and for the objects' queue
M.FAR_BUDGET_MS = 2        -- and for the far ground tiles
M.COL_BUDGET_MS = 4        -- and for the collision cells (ProceduralMesh, ~1.7 us a triangle: a 2,500 piece is ~4 ms)
M.SWAP_QUIET_FRAMES = 3    -- no collision rebuild this many frames and ms after a terrain swap: a rebuild in between
M.SWAP_QUIET_MS = 150      -- took the block before its heights were in (BeamNG.Earth roads.lua, a car fell through)
M.HYST_M = 48              -- the car's tile changes only this far past its edge (michi's drive, 2026-10-26: the
                           -- window and the collision went back and forth along a tile edge)
M.MAP_RESET_FRAMES = 30   -- the AI map is read again this many frames after a terrain swap: the AI DecalRoads clip
                           -- to the terrain, so outside the window their nodes are at z 0 (laptop run 3: 14-19 k of
                           -- 20,810 nodes; a map.reset() after the window came gave every node within 300 m its height)
M.TEMP = '/temp/ticino/'
M.PERF_FILE = '/ticino_perf.csv'
M.TERRAIN_NAME = 'theTerrain'
M.GROUP = 'ticino_stream'

local st = nil

-- ------------------------------------------------------------------ helpers
local function clockFn()
  local hp = rawget(_G, 'hptimer')
  if hp then
    local ok, t = pcall(hp)
    if ok and t and t.stopAndReset then
      local acc = 0
      t:stopAndReset()
      return function() acc = acc + t:stopAndReset(); return acc end
    end
  end
  return function() return os.clock() * 1000 end
end
local clock = clockFn()

local function sta() return rawget(_G, 'simTimeAuthority') end

local function pause(on)
  local s = sta()
  if not s or not s.pause then return end
  if on then
    st.wasPaused = s.getPause and s.getPause() or false
    s.pause(true)
  elseif not st.wasPaused then
    s.pause(false)
  end
end

local function focus()
  if st.focus then return st.focus[1], st.focus[2] end
  if not st.useCamera then
    local veh = getPlayerVehicle and getPlayerVehicle(0)
    if veh then
      local p = veh:getPosition()
      return p.x, p.y
    end
  end
  if core_camera and core_camera.getPositionXYZ then
    local x, y = core_camera.getPositionXYZ()
    return x, y
  end
  return nil
end

local function cellOf(x, y)
  local c = st.cfg
  local m = c.cell * c.square
  return math.floor((x - c.origin[1]) / m), math.floor((y - c.origin[2]) / m)
end

-- the car's tile, kept until the car is HYST_M past its edge
local function cellHyst(x, y)
  local cx, cy = cellOf(x, y)
  local c = st.cell
  if not c then return cx, cy end
  local cfg = st.cfg
  local m = cfg.cell * cfg.square
  local x0, y0 = cfg.origin[1] + c[1] * m, cfg.origin[2] + c[2] * m
  local h = M.HYST_M
  if x >= x0 - h and x < x0 + m + h and y >= y0 - h and y < y0 + m + h then return c[1], c[2] end
  return cx, cy
end

-- the window's tile origin that keeps tile c the 4th or 5th of n (0-based 3 or 4) from wc
local function follow(c, wc, n)
  local lo, hi = n / 2 - 1, n / 2
  if c - wc < lo then return c - lo end
  if c - wc > hi then return c - hi end
  return wc
end

local function perfLine(t)
  st.perf[#st.perf + 1] = t
  local cols = { 'time', 'kind', 'wx', 'wy', 'buildMs', 'buildFrames', 'applyMs', 'grassMs', 'farMs', 'worstFrameMs',
                 'objsQueued', 'reloadMs', 'live', 'colliders', 'colCells', 'afterReloadWorstMs', 'afterReloadSlowFrames' }
  local lines = { table.concat(cols, ',') }
  for _, r in ipairs(st.perf) do
    local v = {}
    for i, k in ipairs(cols) do v[i] = r[k] ~= nil and (type(r[k]) == 'number' and string.format('%.2f', r[k]) or tostring(r[k])) or '' end
    lines[#lines + 1] = table.concat(v, ',')
  end
  pcall(writeFile, M.PERF_FILE, table.concat(lines, '\n') .. '\n')
end

-- ------------------------------------------------------------------ window files
-- A coroutine that writes the window at (wx, wy) and returns its files. yieldFn decides when to give the frame back.
local function makeJob(wx, wy)
  st.serial = st.serial + 1
  local serial = st.serial
  local job = { wx = wx, wy = wy, serial = serial, ms = 0, frames = 0 }
  job.co = coroutine.create(function(yieldFn)
    local parts = terwin.terParts(st.tcache, st.cfg, wx, wy, yieldFn)
    job.ter = M.TEMP .. 'w' .. serial .. '.ter'
    assert(terwin.writeParts(job.ter, parts, yieldFn))
    parts = nil
    job.base = {}
    for _, key in ipairs(st.cfg.baseTextures or {}) do
      local parts = terwin.basePngParts(st.bcache, st.cfg, key, wx, wy, yieldFn)
      local p = M.TEMP .. key .. '_' .. serial .. '.png'
      assert(terwin.writeParts(p, parts, yieldFn))
      job.base[key] = p
      yieldFn()
    end
    return true
  end)
  return job
end

-- Run the job for budgetMs (nil: to the end). Returns true when it is finished.
local function runJob(job, budgetMs)
  local t0 = clock()
  -- the coroutine keeps the yield function of its first resume: it reads this frame's start and budget from the job
  job.t0, job.budget = t0, budgetMs
  local yieldFn = function() if job.budget and clock() - job.t0 > job.budget then coroutine.yield() end end
  local ok, err = coroutine.resume(job.co, yieldFn)
  job.ms = job.ms + (clock() - t0)
  job.frames = job.frames + 1
  if not ok then
    log('E', 'ticino', 'window files failed: ' .. tostring(err))
    job.failed = true
    return true
  end
  return coroutine.status(job.co) == 'dead'
end

local function removeFiles(job)
  if not job then return end
  local fs = { job.ter }
  for _, p in pairs(job.base or {}) do fs[#fs + 1] = p end
  for _, p in ipairs(fs) do
    if p and FS:fileExists(p) then pcall(function() FS:removeFile(p) end) end
  end
end

-- Swap the finished job's window in (one frame).
local function apply(job, kind)
  local cfg = st.cfg
  local t0 = clock()
  local unit = cfg.baseSizeUnit == 'metres' and cfg.square or 1
  local size = tostring(cfg.window * unit)
  for _, bm in ipairs(st.baseMats) do
    local p = job.base[bm.key]
    if p then
      bm.obj:setField('baseColorBaseTex', 0, p)
      bm.obj:setField('baseColorBaseTexSize', 0, size)
    end
  end
  local tb = st.tb
  tb:setField('maxHeight', 0, tostring(cfg.maxHeight))
  tb:setPosition(vec3(cfg.origin[1] + job.wx * cfg.square, cfg.origin[2] + job.wy * cfg.square, cfg.z0))
  tb:setField('terrainFile', 0, job.ter)
  tb:postApply()
  local tApply = clock() - t0
  local flush = rawget(_G, 'flushGroundCoverGrids')
  if flush then pcall(flush) end
  local tGrass = clock() - t0 - tApply
  st.window = { job.wx, job.wy }
  local n = cfg.window / cfg.cell
  local cx, cy = st.cell and st.cell[1] or job.wx / cfg.cell + n / 2 - 1, st.cell and st.cell[2] or job.wy / cfg.cell + n / 2 - 1
  objects.updateFar(cx, cy, job.wx / cfg.cell, job.wy / cfg.cell, n)
  local tFar = clock() - t0 - tApply - tGrass
  removeFiles(st.prevJob)
  st.prevJob = st.curJob
  st.curJob = job
  st.moves = st.moves + 1
  st.quiet = { frames = M.SWAP_QUIET_FRAMES, ms = M.SWAP_QUIET_MS }
  if M.MAP_RESET_FRAMES then st.mapResetIn = M.MAP_RESET_FRAMES end
  st.watch = { frames = 10, worst = 0, rec = { time = os.date('%H:%M:%S'), kind = kind, wx = job.wx, wy = job.wy,
    buildMs = job.ms, buildFrames = job.frames, applyMs = tApply, grassMs = tGrass, farMs = tFar } }
  log('I', 'ticino', string.format('%s: window at (%d, %d): files %.0f ms in %d frames, swap %.1f ms, grass %.1f ms',
    kind, job.wx, job.wy, job.ms, job.frames, tApply, tGrass))
end

-- ------------------------------------------------------------------ jump (spawn, teleport)
local function jump(x, y)
  local cfg = st.cfg
  local n = cfg.window / cfg.cell
  local cx, cy = cellOf(x, y)
  local wcx, wcy = cx - (n / 2 - 1), cy - (n / 2 - 1)
  pause(true)
  st.job = nil
  local job = makeJob(wcx * cfg.cell, wcy * cfg.cell)
  runJob(job, nil)
  st.cell = { cx, cy }
  if not job.failed then apply(job, 'jump') end
  objects.retarget(cx, cy)
  objects.step(clock, nil)
  objects.updateCols(x, y, true)
  objects.stepCols(clock, nil)
  -- the collision rebuild waits for the swapped terrain (SWAP_QUIET_FRAMES), the game stays paused till after it
  st.jumpReload = true
  st.resumeIn = M.SWAP_QUIET_FRAMES + 2
end

-- Rebuild collision if something collides anew or no more, unless a terrain swap is too recent; rec gets reloadMs
-- and is logged (with the frames after it). Returns true when no rebuild is pending any more.
local function tryReload(rec)
  local q = st.quiet
  if q then
    if q.frames > 0 or q.ms > 0 then return false end
    st.quiet = nil
  end
  local ms = objects.reloadCollisionIfDirty(clock)
  if rec then
    rec.reloadMs = ms
    local s = objects.stats()
    rec.live, rec.colliders, rec.colCells = s.live, s.colliders, s.colCells
    st.rwatch = { frames = 90, worst = 0, slow = 0, rec = rec }
  end
  return true
end

-- ------------------------------------------------------------------ hooks
local function start()
  local cfgText = readFile('/levels/' .. M.LEVEL .. '/stream.json')
  local ok, cfg = pcall(jsonDecode, cfgText or '')
  if not ok or type(cfg) ~= 'table' then
    log('E', 'ticino', 'stream.json not readable: streaming off')
    return
  end
  local tb = scenetree.findObject(M.TERRAIN_NAME)
  if not tb then
    log('E', 'ticino', 'no TerrainBlock ' .. M.TERRAIN_NAME .. ': streaming off')
    return
  end
  if not FS:directoryExists(M.TEMP) then FS:directoryCreate(M.TEMP, true) end
  local group = scenetree.findObject(M.GROUP)
  if not group then
    group = createObject('SimGroup')
    group.canSave = false
    group:registerObject(M.GROUP)
    scenetree.MissionGroup:addObject(group)
  end
  st = { cfg = cfg, tb = tb, group = group, serial = 0, moves = 0, perf = {},
         tcache = terwin.newCache('/levels/' .. M.LEVEL .. '/blocks/terrain/', 16),
         bcache = terwin.newCache('/levels/' .. M.LEVEL .. '/blocks/base/', 12 * #(cfg.baseTextures or {})),
         window = { cfg.start[1], cfg.start[2] }, baseMats = {}, started = true }
  -- the terrain materials whose base colour is the window's map
  for _, bm in ipairs(cfg.baseMaterials or {}) do
    local o = scenetree.findObject(bm[1])
    if not o then
      for _, name in ipairs(scenetree.findClassObjects('TerrainMaterial') or {}) do
        local m = scenetree.findObject(name)
        if m and m:getField('internalName', 0) == bm[2] then o = m; break end
      end
    end
    if o then st.baseMats[#st.baseMats + 1] = { obj = o, key = bm[3] }
    else log('W', 'ticino', 'terrain material not found: ' .. bm[1]) end
  end
  objects.init(cfg, M.LEVEL, group)
  log('I', 'ticino', string.format('streaming on: zone %s, %d blocks a side, %d tiles of objects, %d far tiles',
    tostring(cfg.zone), cfg.blocksPerSide or 0, tableSize and tableSize(cfg.tiles) or 0, #(cfg.far or {})))
end

local function stop()
  if not st then return end
  objects.clear()
  removeFiles(st.prevJob)
  removeFiles(st.curJob)
  if st.job then removeFiles(st.job) end
  st = nil
end

local function onUpdate(dtReal)
  if not st then return end
  if st.quiet then                    -- frames and real time since the last terrain swap
    st.quiet.frames = st.quiet.frames - 1
    st.quiet.ms = st.quiet.ms - (dtReal or 0) * 1000
  end
  if st.resumeIn then
    if st.resumeIn == 2 and st.jumpReload then
      st.jumpReload = nil
      st.quiet = nil
      local ms = objects.reloadCollisionIfDirty(clock)
      if st.watch then st.watch.rec.reloadMs = ms end
    end
    st.resumeIn = st.resumeIn - 1
    if st.resumeIn <= 0 then
      st.resumeIn = nil
      pause(false)
    end
    return
  end
  if st.rwatch then
    local w = st.rwatch
    local ms = (dtReal or 0) * 1000
    w.worst = math.max(w.worst, ms)
    if ms > 100 then w.slow = w.slow + 1 end
    w.frames = w.frames - 1
    if w.frames <= 0 then
      w.rec.afterReloadWorstMs, w.rec.afterReloadSlowFrames = w.worst, w.slow
      perfLine(w.rec)
      st.rwatch = nil
    end
  end
  if st.watch then
    local w = st.watch
    w.worst = math.max(w.worst, (dtReal or 0) * 1000)
    w.frames = w.frames - 1
    if w.frames <= 0 then
      w.rec.worstFrameMs = w.worst
      local s = objects.stats()
      w.rec.live, w.rec.colliders = s.live, s.colliders
      perfLine(w.rec)
      st.watch = nil
    end
  end
  if st.mapResetIn and not st.resumeIn then
    st.mapResetIn = st.mapResetIn - 1
    if st.mapResetIn <= 0 then
      st.mapResetIn = nil
      local t0 = clock()
      local ok = pcall(function() map.reset() end)
      local ms = clock() - t0
      perfLine({ time = os.date('%H:%M:%S'), kind = 'mapreset', wx = st.window[1], wy = st.window[2], applyMs = ms })
      log('I', 'ticino', string.format('AI map read again after the window move: %.1f ms%s', ms, ok and '' or ' (failed)'))
    end
  end
  local x, y = focus()
  if not x then return end
  local cfg = st.cfg
  local n = cfg.window / cfg.cell
  local cx, cy = cellOf(x, y)
  local wcx, wcy = st.window[1] / cfg.cell, st.window[2] / cfg.cell
  -- a jump: the first frame, or the car more than a tile out of its place in the window
  if st.started or cx - wcx < 1 or cx - wcx > n - 2 or cy - wcy < 1 or cy - wcy > n - 2 then
    st.started = nil
    jump(x, y)
    return
  end
  cx, cy = cellHyst(x, y)
  if objects.updateCols(x, y) and not st.objRec then
    local c = objects.colCell and objects.colCell()
    st.objRec = { time = os.date('%H:%M:%S'), kind = 'colcell', wx = c and c[1], wy = c and c[2], objsQueued = 0 }
  end
  if not st.cell or st.cell[1] ~= cx or st.cell[2] ~= cy then
    st.cell = { cx, cy }
    local q = objects.retarget(cx, cy)
    st.objRec = { time = os.date('%H:%M:%S'), kind = 'tile', wx = cx, wy = cy, objsQueued = q }
    objects.updateFar(cx, cy, wcx, wcy, n)
    return            -- the window work waits for the next frame
  end
  -- the collision cells round the car (ProceduralMesh pieces, a few ms a frame)
  if objects.colsPending() then
    objects.stepCols(clock, M.COL_BUDGET_MS)
    if objects.colsPending() then return end
  end
  -- the collision rebuild first, as soon as the cells and the colliders of the queue (it starts with them) are made
  -- and no terrain swap is too recent: the window's files and the drawn objects wait a frame
  if objects.colDirty() and not objects.colsPending() and not objects.collidersPending() and tryReload(st.objRec) then
    st.objRec = nil
    return
  end
  -- the window
  local tx, ty = follow(cx, wcx, n), follow(cy, wcy, n)
  if tx ~= wcx or ty ~= wcy then
    if not st.job or st.job.wx ~= tx * cfg.cell or st.job.wy ~= ty * cfg.cell then
      if st.job then removeFiles(st.job) end
      st.job = makeJob(tx * cfg.cell, ty * cfg.cell)
    end
  end
  if st.job then
    if runJob(st.job, M.BUDGET_MS) then
      local job = st.job
      st.job = nil
      if not job.failed then apply(job, 'move') end
    end
    return            -- the objects wait for a frame without window work
  end
  -- the objects
  if objects.pending() then
    objects.step(clock, M.OBJ_BUDGET_MS)
  elseif st.objRec then
    perfLine(st.objRec)
    st.objRec = nil
  elseif not objects.farPending() then
    objects.prefetch(1)
  else
    objects.stepFar(clock, M.FAR_BUDGET_MS)
  end
end

local function onClientPostStartMission(levelPath)
  stop()
  if type(levelPath) == 'string' and levelPath:find('/levels/' .. M.LEVEL .. '/', 1, true) then start() end
end

local function onClientEndMission()
  stop()
end

-- ------------------------------------------------------------------ console
function M.status()
  if not st then return 'off' end
  local s = objects.stats()
  return { window = st.window, cell = st.cell, moves = st.moves, job = st.job and { st.job.wx, st.job.wy } or nil,
           objects = s, last = st.perf[#st.perf], tcacheMisses = st.tcache.misses, bcacheMisses = st.bcache.misses }
end

-- Collision at run time (tests): radius in tiles, list of groups that never collide (e.g. {'level_objects/terrain_skin'}).
function M.setCollision(radius, groupsOff)
  if not st then return 'off' end
  local q = objects.setCollision(radius, groupsOff)
  st.objRec = { time = os.date('%H:%M:%S'), kind = 'collision', objsQueued = q }
  return q
end

-- Collision cells within r of the car's cell (-1: none), for tests; the rebuild follows as for a cell change.
function M.setColRadius(r)
  if not st then return 'off' end
  local ch = objects.setColRadius(r)
  st.objRec = { time = os.date('%H:%M:%S'), kind = 'colradius', wx = r, objsQueued = 0 }
  return ch
end

function M.setFocus(x, y)
  if not st then return end
  st.focus = x and { x, y } or nil
end

function M.followCamera(on)
  if st then st.useCamera = on and true or false end
end

function M.dropAIRoads()
  local m = map and map.getMap and map.getMap()
  if not m or not m.nodes or next(m.nodes) == nil then return 'the AI map is not built yet' end
  local g = scenetree.findObject('AIRoads')
  if not g then return 'no AIRoads group' end
  local ids = {}
  for i = 0, g:getCount() - 1 do
    local r = g:getObject(i)
    if r and r:getClassName() == 'DecalRoad' then ids[#ids + 1] = r:getID() end
  end
  local n = 0
  for _, id in ipairs(ids) do
    local r = scenetree.findObjectById(id)
    if r then r:delete(); n = n + 1 end
  end
  return n .. ' AI roads deleted (the AI map stays as it was built)'
end

M.onUpdate = onUpdate
M.onClientPostStartMission = onClientPostStartMission
M.onClientEndMission = onClientEndMission
M.onExtensionUnloaded = stop
-- for tests
M._follow = follow

return M
