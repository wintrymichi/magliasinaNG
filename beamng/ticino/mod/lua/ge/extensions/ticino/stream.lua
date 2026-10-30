-- Ticino streaming (GE extension 'ticino_stream'): one TerrainBlock of 2048 x 2048 samples that follows the car,
-- put together from the zone's blocks, and the objects of the 384 m tiles around it (beamng/ticino/README.md).
-- Active only in the level 'ticino'.
--
-- Tried on michi's PC (2026-10-28): the window moves when the car's tile leaves the places
-- FOLLOW_LO..FOLLOW_HI of its 8, and then so far that the car lands at the other end of them (a move froze the game
-- ~1 s: once a tile was one every ~20 s of driving); every 5 s of frame times go to <user folder>/ticino_frames.csv.
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
-- With "diagnostics": true in <user folder>/settings/ticino.json every move is logged to <user folder>/ticino_perf.csv.

local terwin = require('ticino/terwin')
local objects = require('ticino/objects')
local forest = require('ticino/forest')
local png = require('ticino/png')
local helper = require('ticino/helper')

local M = {}

M.LEVEL = 'ticino'
M.BUDGET_MS = 4            -- Lua time a frame for the next window's files
M.OBJ_BUDGET_MS = 3        -- and for the objects' queue
M.NEAR_RINGS = 1           -- the objects of the tiles this near the car's (Chebyshev) come before the window's files
M.FAR_BUDGET_MS = 2        -- and for the far ground tiles
M.FOREST_BUDGET_MS = 3     -- and for the forest items (forest.lua, also at most forest.PER_FRAME items)
M.FOREST_JUMP_MS = 1000    -- forest items made at a jump, while the game is paused (3000 made the jump frame 6-7 s)
M.FAR_JUMP_MS = 500        -- far ground tiles made at a jump (the mountains round the new place; the rest comes after)
M.OBJ_JUMP_MS = 1500       -- objects of rings 1..NEAR_RINGS made at a jump (ring 0 is always made whole)
M.FAR_EVERY_MS = 1         -- far ground made each frame beside the objects' queue (it came only when all was idle)
M.NO_DYNAMIC_CUBEMAP = false  -- turn off dynamicCubemap on the level's materials at the start (PC test 2026-10-30)
M.BURST_EVERY_MS = 1000    -- > 0: the far objects, trees and far ground come in bursts of BURST_MS once every this
M.BURST_MS = 40            -- many ms, not a few ms in every frame (each frame that changes the scene costs the engine:
                           -- PC test 2026-10-30, Lugano flight 47 fps with 3 ms a frame, 94 with 40 ms bursts a second)
M.BURST_EVERY_SLOW_MS = 200  -- bursts this often while the car is slower than SLOW_MPS (standing: the queue of a
M.SLOW_MPS = 4               -- new place, ~8 ms an object in the game, took minutes at one burst a second)
M.COL_BUDGET_MS = 4        -- and for the collision cells (ProceduralMesh, ~1.7 us a triangle: a 2,500 piece is ~4 ms)
M.SWAP_QUIET_FRAMES = 3    -- no collision rebuild this many frames and ms after a terrain swap: a rebuild in between
M.SWAP_QUIET_MS = 150      -- took the block before its heights were in (BeamNG.Earth roads.lua, a car fell through)
M.FOLLOW_LO = 2            -- the car's tile may be the 3rd to the 6th of the window's 8 (0-based 2..5): the car is at
M.FOLLOW_HI = 5            -- least 2 tiles (768 m) from its edge, a straight drive moves the window every 4 tiles
M.FRAMES_FILE = '/ticino_frames.csv'
M.FRAMES_EVERY_MS = 5000
M.SLOW_FRAME_MS = 120      -- a frame longer than this is logged with what the streamer did in it
M.TB_BASE_TEX_SIZE = 0     -- > 0: the TerrainBlock's baseTexSize (the level has 1024), set at the start (tests)
M.BASE_MODE = 'swap'       -- base colour maps at a move: 'swap' (same frame), 'split' (a material a frame), 'jump'
M.POS_MODE = 'setPosition' -- how the block moves: 'setPosition' (0.1-0.16 s on its own) or 'field' (position field,
                           -- then terrainFile: checked after the swap, back to setPosition if the block did not move)
M.RELOAD_DEFER_MS = 3000   -- a rebuild only for props or trees waits for the next one of the collision cells, at most this
M.BASE_COMBINED = true     -- one base colour map for all the streamed materials (each pixel from the map of the material
                           -- under it): the game re-packs one texture at a move instead of 7 (~45 ms each)
M.DROP_AI_ROADS = true     -- delete the 12,639 invisible AI DecalRoads once the first jump has read the AI map: each
                           -- re-clipped itself at every terrain move (0.1-0.35 s of the swap); later jumps keep that map
M.CFG_FILE = '/ticino_stream_cfg.json'   -- optional: { "stream": {..}, "objects": {..}, "forest": {..} } fields to override
M.SETTINGS_FILE = '/settings/ticino.json' -- the player's settings (README "Settings"): preset, helper, diagnostics, ...
M.DIAG = false             -- write ticino_frames.csv and ticino_perf.csv (settings "diagnostics"; the log lines stay)
-- Presets of the settings file. "standard" is the level as built and tested; "light" is for PCs with little VRAM or
-- a slow CPU: trees drawn nearer, far ground less far (the near scene stays the same).
M.PRESETS = {
  standard = {},
  light = { forest = { RADIUS = 3, SHARE = { [0] = 1.0, 1.0, 0.5, 0.25 }, CACHE_TILES = 80 },
            objects = { CACHE_TILES = 250 }, level = { farRadius = 10 } },
}
M.HYST_M = 48              -- the car's tile changes only this far past its edge (michi's drive, 2026-10-26: the
                           -- window and the collision went back and forth along a tile edge)
M.MAP_RESET_ON_JUMP = true -- read the AI map again at a jump, while the game is paused (1.9-2.5 s on the laptop)
M.MAP_RESET_FRAMES = nil  -- frames after a terrain swap to read the AI map again (nil: never). A map.reset() fixed
                           -- the z 0 nodes near the car but froze the laptop 2-2.5 s every move (run 4); the AI roads
                           -- now have useSubdivisions off (blocks.py), so the graph takes their own heights
M.TEMP = '/temp/ticino/'
M.PERF_FILE = '/ticino_perf.csv'
M.TERRAIN_NAME = 'theTerrain'
M.HELPER = true            -- use the helper process's window files when it runs (ticino/helper.lua)
M.HELPER_WAIT_MS = 8000    -- at a jump, wait this long for the helper's window before making it in Lua
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

-- the window's tile origin that keeps tile c within the places FOLLOW_LO..FOLLOW_HI of n from wc; when it has to move,
-- c lands at the other end of them. Never nearer than 1 tile to the edge: closer is a jump (onUpdate).
local function followPlaces(n)
  return math.max(1, math.min(M.FOLLOW_LO, n / 2 - 1)), math.min(n - 2, math.max(M.FOLLOW_HI, n / 2))
end

local function follow(c, wc, n)
  local lo, hi = followPlaces(n)
  if c - wc < lo then return c - hi end
  if c - wc > hi then return c - lo end
  return wc
end

-- frame times: every FRAMES_EVERY_MS one line of fps, the worst frame, frames over 50 and 100 ms, moves and rebuilds
local function frameStats()
  local now = clock()
  local f = st.frames
  if not f then
    st.frames = { t0 = now, last = now, n = 0, worst = 0, over50 = 0, over100 = 0, moves = st.moves, reloads = st.reloads,
                  lines = { 'time,seconds,fps,worstMs,over50,over100,moves,reloads' } }
    return
  end
  local d = now - f.last
  f.last = now
  f.n = f.n + 1
  if d > M.SLOW_FRAME_MS then          -- what the streamer did in that frame (st.act, set by onUpdate)
    log('W', 'ticino', string.format('slow frame %.0f ms, streamer: %s', d, tostring(st.act)))
  end
  st.act = 'idle'
  local a = st.afterSwap               -- the frames right after a swap (the frame of the swap is next1Ms)
  if a then
    a.n = a.n + 1
    a.rec['next' .. a.n .. 'Ms'] = d
    if a.n >= 4 then st.afterSwap = nil end
  end
  if d > f.worst then f.worst = d end
  if d > 50 then f.over50 = f.over50 + 1 end
  if d > 100 then f.over100 = f.over100 + 1 end
  local span = now - f.t0
  if span < M.FRAMES_EVERY_MS then return end
  f.lines[#f.lines + 1] = string.format('%s,%.1f,%.1f,%.0f,%d,%d,%d,%d', os.date('%H:%M:%S'), span / 1000,
    f.n * 1000 / span, f.worst, f.over50, f.over100, st.moves - f.moves, st.reloads - f.reloads)
  if #f.lines > 2000 then table.remove(f.lines, 2) end
  if M.DIAG then pcall(writeFile, M.FRAMES_FILE, table.concat(f.lines, '\n') .. '\n') end
  f.t0, f.n, f.worst, f.over50, f.over100, f.moves, f.reloads = now, 0, 0, 0, 0, st.moves, st.reloads
end

local function perfLine(t)
  st.perf[#st.perf + 1] = t
  local cols = { 'time', 'kind', 'wx', 'wy', 'buildMs', 'buildFrames', 'applyMs', 'grassMs', 'farMs', 'worstFrameMs',
                 'objsQueued', 'reloadMs', 'live', 'colliders', 'colCells', 'afterReloadWorstMs', 'afterReloadSlowFrames',
                 'baseMs', 'posMs', 'terMs', 'postMs', 'next1Ms', 'next2Ms', 'next3Ms', 'next4Ms', 'nearMs', 'helper', 'helperWaitMs' }
  local lines = { table.concat(cols, ',') }
  for _, r in ipairs(st.perf) do
    local v = {}
    for i, k in ipairs(cols) do v[i] = r[k] ~= nil and (type(r[k]) == 'number' and string.format('%.2f', r[k]) or tostring(r[k])) or '' end
    lines[#lines + 1] = table.concat(v, ',')
  end
  if M.DIAG then pcall(writeFile, M.PERF_FILE, table.concat(lines, '\n') .. '\n') end
end

-- ------------------------------------------------------------------ window files
-- The window's base colour rows of texture `key` (PNG rows from the north), as terwin.basePngParts reads them.
local function baseRows(key, wx, wy, yieldFn)
  local cfg = st.cfg
  local P = cfg.basePx
  local B, W = cfg.block / P, cfg.window / P
  local x0, y0 = wx / P, wy / P
  local out = {}
  for i = 0, W - 1 do
    local gy = y0 + (W - 1 - i)
    local by = math.floor(gy / B)
    local br = gy - by * B
    local parts, c = {}, 0
    while c < W do
      local gx = x0 + c
      local bx = math.floor(gx / B)
      local bc = gx - bx * B
      local k = math.min(B - bc, W - c)
      local misses = st.bcache.misses
      local s = st.bcache:get(key .. '_' .. bx .. '_' .. by .. '.rgb')
      if st.bcache.misses ~= misses then yieldFn() end
      if s then
        local a = br * B * 3 + bc * 3 + 1
        parts[#parts + 1] = s:sub(a, a + k * 3 - 1)
      else
        parts[#parts + 1] = string.rep('\128\128\128', k)
      end
      c = c + k
    end
    out[i + 1] = table.concat(parts)
    if i % 128 == 127 then yieldFn() end
  end
  return out
end

-- BASE_COMBINED: one map whose every pixel comes from the base map of the material under its centre sample (the
-- .ter's layer rows: terParts[W + 3 + row from the south]); materials without a streamed map take the first one.
local function combinedRows(terParts, wx, wy, yieldFn)
  local cfg = st.cfg
  local P, W = cfg.basePx, cfg.window
  local Wp = W / P
  local half = math.floor(P / 2)
  local keyRows, keyIdx = {}, {}
  for i, key in ipairs(cfg.baseTextures) do
    keyRows[i] = baseRows(key, wx, wy, yieldFn)
    keyIdx[key] = i
  end
  local lk = {}
  for li, name in ipairs(cfg.materials or {}) do
    local key = st.layerKey[name]
    lk[li - 1] = key and keyIdx[key] or 1
  end
  local out = {}
  for i = 0, Wp - 1 do
    local rs = Wp - 1 - i
    local lrow = terParts[W + 3 + rs * P + half]
    local buf = {}
    for x = 0, Wp - 1 do
      local src = keyRows[lk[lrow:byte(x * P + half + 1)] or 1][i + 1]
      buf[x + 1] = src:sub(3 * x + 1, 3 * x + 3)
    end
    out[i + 1] = table.concat(buf)
    if i % 32 == 31 then yieldFn() end
  end
  return out
end

-- A block cache that gives the frame back (yieldFn) after every block it had to read: a 4.9 MB terrain block took
-- 20-50 ms, a move read 2-4 of them in one frame (150-230 ms frames in the highway test)
local function yieldingCache(cache, yieldFn)
  return { get = function(_, name)
    local misses = cache.misses
    local d = cache:get(name)
    if cache.misses ~= misses then yieldFn() end
    return d
  end }
end

-- A coroutine that writes the window at (wx, wy) and returns its files. yieldFn decides when to give the frame back.
local function makeJob(wx, wy)
  st.serial = st.serial + 1
  local serial = st.serial
  local job = { wx = wx, wy = wy, serial = serial, ms = 0, frames = 0 }
  -- the helper's files, if it has the window ready (only the combined base map: the helper makes no other)
  local h = M.HELPER and M.BASE_COMBINED and st.layerKey and helper.take(wx, wy)
  if h then
    job.ter, job.base, job.helper = h.ter, { combined = h.base }, true
    job.co = coroutine.create(function() return true end)
    return job
  end
  job.co = coroutine.create(function(yieldFn)
    local parts = terwin.terParts(yieldingCache(st.tcache, yieldFn), st.cfg, wx, wy, yieldFn)
    job.ter = M.TEMP .. 'w' .. serial .. '.ter'
    assert(terwin.writeParts(job.ter, parts, yieldFn))
    job.base = {}
    if M.BASE_COMBINED and st.layerKey then
      local ok, err = pcall(function()
        local Wp = st.cfg.window / st.cfg.basePx
        local rows = combinedRows(parts, wx, wy, yieldFn)
        local p = M.TEMP .. 'base_' .. serial .. '.png'
        assert(terwin.writeParts(p, png.parts(rows, Wp, Wp, yieldFn), yieldFn))
        job.base.combined = p
      end)
      if not ok then
        log('E', 'ticino', 'combined base map failed, back to one map a material: ' .. tostring(err))
        M.BASE_COMBINED = false
      end
    end
    parts = nil
    for _, key in ipairs(job.base.combined and {} or st.cfg.baseTextures or {}) do
      local parts = terwin.basePngParts(yieldingCache(st.bcache, yieldFn), st.cfg, key, wx, wy, yieldFn)
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

-- the base colour maps of the job's window on the terrain materials (all, or only those of list)
local function setBase(job, list)
  local cfg = st.cfg
  local unit = cfg.baseSizeUnit == 'metres' and cfg.square or 1
  local size = tostring(cfg.window * unit)
  if #st.baseMats == 0 then log('W', 'ticino', 'no terrain material takes the base colour map') end
  for _, bm in ipairs(list or st.baseMats) do
    local p = job.base.combined or job.base[bm.key]
    if p then
      if list == nil and not FS:fileExists(p) then log('W', 'ticino', 'base colour map missing: ' .. p) end
      bm.obj:setField('baseColorBaseTex', 0, p)
      bm.obj:setField('baseColorBaseTexSize', 0, size)
    end
  end
end

-- Swap the finished job's window in (one frame). BASE_MODE 'swap': the base colour maps in the same frame;
-- 'split': one material a frame after it (st.basePending); 'jump': only at a jump (a move keeps the old maps).
local function apply(job, kind)
  local cfg = st.cfg
  local t0 = clock()
  local mode = kind == 'jump' and 'swap' or M.BASE_MODE
  if mode == 'swap' then setBase(job) end
  local tBase = clock() - t0
  local tb = st.tb
  local px, py, pz = cfg.origin[1] + job.wx * cfg.square, cfg.origin[2] + job.wy * cfg.square, cfg.z0
  tb:setField('maxHeight', 0, tostring(cfg.maxHeight))
  if M.POS_MODE == 'field' then
    tb:setField('position', 0, string.format('%.3f %.3f %.3f', px, py, pz))
  else
    tb:setPosition(vec3(px, py, pz))
  end
  local tPos = clock() - t0 - tBase
  tb:setField('terrainFile', 0, job.ter)
  local tTer = clock() - t0 - tBase - tPos
  tb:postApply()
  local p = tb:getPosition()
  if math.abs(p.x - px) > 0.5 or math.abs(p.y - py) > 0.5 or math.abs(p.z - pz) > 0.5 then
    log('W', 'ticino', string.format('terrain at (%.1f, %.1f, %.1f) after the swap, not (%.1f, %.1f, %.1f): setPosition',
      p.x, p.y, p.z, px, py, pz))
    M.POS_MODE = 'setPosition'
    tb:setPosition(vec3(px, py, pz))
  end
  local tPost = clock() - t0 - tBase - tPos - tTer
  local tApply = clock() - t0
  if mode == 'split' then
    st.basePending = { job = job, i = 1 }
  end
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
    buildMs = job.ms, buildFrames = job.frames, applyMs = tApply, grassMs = tGrass, farMs = tFar,
    baseMs = tBase, posMs = tPos, terMs = tTer, postMs = tPost, helper = job.helper and 1 or 0, helperWaitMs = job.waitMs } }
  st.afterSwap = { rec = st.watch.rec, n = 0 }
  log('I', 'ticino', string.format('%s: window at (%d, %d): files %.0f ms in %d frames' .. (job.helper and ' (helper)' or '') .. ', swap %.1f ms (base %.1f, '
    .. 'position %.1f, terrainFile %.1f, postApply %.1f), grass %.1f ms', kind, job.wx, job.wy, job.ms, job.frames,
    tApply, tBase, tPos, tTer, tPost, tGrass))
end

-- ------------------------------------------------------------------ jump (spawn, teleport)
local function jump(x, y)
  local cfg = st.cfg
  local n = cfg.window / cfg.cell
  local cx, cy = cellOf(x, y)
  local wcx, wcy = cx - (n / 2 - 1), cy - (n / 2 - 1)
  local T = { t0 = clock() }
  local function mark(k) T[k] = clock() - T.t0 end
  log('I', 'ticino', string.format('jump to (%.0f, %.0f), tile (%d, %d), window (%d, %d)', x, y, cx, cy, wcx, wcy))
  pause(true)
  if st.job then removeFiles(st.job) end
  st.job = nil
  if M.HELPER and M.BASE_COMBINED and helper.alive(true) then
    local w = { wcx * cfg.cell, wcy * cfg.cell }
    local lo, hi = followPlaces(n)
    helper.request(x, y, w, lo, hi, n, w)
    helper.wait(w[1], w[2], M.HELPER_WAIT_MS)
  end
  local job = makeJob(wcx * cfg.cell, wcy * cfg.cell)
  if M.HELPER then job.waitMs = helper.stats().lastWaitMs end
  runJob(job, nil)
  mark('files')
  -- a jump farther than the objects reach (Manno -> Bellinzona, PC 2026-10-30): the old place has nothing the new one
  -- needs. Its objects and trees go at once here, while paused; else their deletions queued behind the new rings and
  -- the new place filled in for minutes.
  local far = not st.cell or math.max(math.abs(cx - st.cell[1]), math.abs(cy - st.cell[2]))
    > math.max(objects.maxRadius(), forest.RADIUS) * 2
  local dropped, felled = 0, 0
  if far and st.cell then
    dropped, felled = objects.dropAll(), forest.clear()
  end
  mark('drop')
  st.cell = { cx, cy }
  if not job.failed then apply(job, 'jump') else log('W', 'ticino', 'jump: the window files failed, terrain not moved') end
  mark('swap')
  objects.retarget(cx, cy)
  -- ring 0 whole, then the near rings up to OBJ_JUMP_MS: with no cap the paused jump frame grew to 8-9 s (PC test of
  -- 79f0e61, every shape of a new zone is a COLLADA import); what is left comes in the next frames, nearest first
  objects.step(clock, nil, 0)
  local tObj = clock()
  while not objects.step(clock, math.max(1, M.OBJ_JUMP_MS - (clock() - tObj)), M.NEAR_RINGS)
    and clock() - tObj < M.OBJ_JUMP_MS and objects.nearPending(M.NEAR_RINGS) do end
  mark('objects')
  objects.updateCols(x, y, true)
  objects.stepCols(clock, nil)
  mark('cols')
  forest.retarget(cx, cy)
  forest.step(clock, M.FOREST_JUMP_MS, 1e9)
  mark('forest')
  objects.stepFar(clock, M.FAR_JUMP_MS)
  mark('far')
  log('I', 'ticino', string.format('jump to tile (%d, %d)%s: %d objects and %d trees of the old place removed, far ground '
    .. '%s; ms files %.0f, drop %.0f, swap %.0f, objects %.0f, cols %.0f, forest %.0f, far %.0f', cx, cy,
    far and ' (far)' or '', dropped, felled, objects.farPending() and 'still queued' or 'made', T.files, T.drop - T.files,
    T.swap - T.drop, T.objects - T.swap, T.cols - T.objects, T.forest - T.cols, T.far - T.forest))
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
  if ms > 0 then st.reloads = st.reloads + 1 end
  if rec then
    rec.reloadMs = ms
    local s = objects.stats()
    rec.live, rec.colliders, rec.colCells = s.live, s.colliders, s.colCells
    st.rwatch = { frames = 90, worst = 0, slow = 0, rec = rec }
  end
  return true
end

-- ------------------------------------------------------------------ hooks
-- Fields of the settings file and of CFG_FILE (tests): only fields that exist, of the same type. "level" fields
-- override stream.json (numbers only, e.g. farRadius).
local function applyFields(over, cfg, what)
  if type(over) ~= 'table' then return end
  for name, mod in pairs({ stream = M, objects = objects, forest = forest }) do
    for k, v in pairs(type(over[name]) == 'table' and over[name] or {}) do
      if mod[k] ~= nil and type(mod[k]) == type(v) then
        mod[k] = v
        log('I', 'ticino', what .. ' ' .. name .. '.' .. k .. ' = ' .. (type(v) == 'table' and 'table' or tostring(v)))
      end
    end
  end
  for k, v in pairs(type(over.level) == 'table' and over.level or {}) do
    if type(cfg[k]) == 'number' and type(v) == 'number' then
      cfg[k] = v
      log('I', 'ticino', what .. ' level.' .. k .. ' = ' .. tostring(v))
    end
  end
end

local function readJson(path)
  local text = readFile(path)
  if not text then return nil end
  local ok, t = pcall(jsonDecode, text)
  if ok and type(t) == 'table' then return t end
  log('W', 'ticino', path .. ' is not valid JSON: ignored')
end

-- The player's settings (SETTINGS_FILE), then the test overrides (CFG_FILE), over the built stream.json (cfg)
local function readSettings(cfg)
  local s = readJson(M.SETTINGS_FILE) or {}
  local preset = type(s.preset) == 'string' and s.preset or 'standard'
  if not M.PRESETS[preset] then
    log('W', 'ticino', 'unknown preset "' .. preset .. '": standard')
    preset = 'standard'
  end
  local W = cfg.window
  applyFields(M.PRESETS[preset], cfg, 'preset ' .. preset .. ':')
  if type(s.helper) == 'boolean' then M.HELPER = s.helper end
  if type(s.diagnostics) == 'boolean' then M.DIAG = s.diagnostics end
  if type(s.dynamicObjects) == 'boolean' then objects.DYNAMIC = s.dynamicObjects end
  applyFields(s, cfg, 'setting')
  applyFields(readJson(M.CFG_FILE), cfg, 'override')
  -- a window size of the settings (level.window, tiles of cfg.cell): the helper writes the built size only
  -- 4 tiles were too few: every move came too late and was a jump (sim, 2026-10-30)
  if cfg.window % cfg.cell ~= 0 or cfg.window / cfg.cell < 6 or cfg.window > W then
    if cfg.window ~= W then log('W', 'ticino', 'window ' .. cfg.window .. ' not usable: ' .. W) end
    cfg.window = W
  end
  if cfg.window ~= W then M.HELPER = false end
  log('I', 'ticino', string.format('settings: preset %s, helper %s, diagnostics %s', preset, tostring(M.HELPER),
    tostring(M.DIAG)))
end

local function start()
  local cfg = readJson('/levels/' .. M.LEVEL .. '/stream.json')
  if not cfg then
    log('E', 'ticino', 'stream.json not readable: streaming off')
    return
  end
  readSettings(cfg)
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
  st = { cfg = cfg, tb = tb, group = group, serial = 0, moves = 0, reloads = 0, perf = {},
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
  if M.TB_BASE_TEX_SIZE > 0 then tb:setField('baseTexSize', 0, tostring(M.TB_BASE_TEX_SIZE)) end
  st.layerKey = {}                    -- terrain material (.ter name) -> its streamed base map (BASE_COMBINED)
  for _, bm in ipairs(cfg.baseMaterials or {}) do st.layerKey[bm[2]] = bm[3] end
  if M.NO_DYNAMIC_CUBEMAP then M.dynamicCubemaps(false) end
  if M.HELPER then helper.init(cfg, clock) end
  objects.init(cfg, M.LEVEL, group)
  forest.init(cfg, M.LEVEL, objects.markColDirty)
  log('I', 'ticino', string.format('streaming on: zone %s, %d blocks a side, %d tiles of objects, %d far tiles',
    tostring(cfg.zone), cfg.blocksPerSide or 0, tableSize and tableSize(cfg.tiles) or 0, #(cfg.far or {})))
  log('I', 'ticino', string.format('stream 2026-10-28: window places %d..%d, base maps %s, collision lazy %d, '
    .. 'frame times to %s', M.FOLLOW_LO, M.FOLLOW_HI, M.BASE_MODE, objects.COL_LAZY or -1, M.FRAMES_FILE))
end

local function stop()
  if not st then return end
  objects.clear()
  forest.clear()
  removeFiles(st.prevJob)
  removeFiles(st.curJob)
  if st.job then removeFiles(st.job) end
  helper.stop()
  st = nil
end

local function onUpdate(dtReal)
  if not st then return end
  frameStats()
  local settled, nSettled = objects.settle(clock)
  if settled and M.DIAG then log('D', 'ticino', nSettled .. ' objects made static') end
  if st.basePending then              -- BASE_MODE 'split': one terrain material's base colour map a frame
    local bp = st.basePending
    local bm = st.baseMats[bp.i]
    if bm then setBase(bp.job, { bm }) end
    bp.i = bp.i + 1
    if bp.i > #st.baseMats then st.basePending = nil end
  end
  if st.quiet then                   -- frames and real time since the last terrain swap
    st.quiet.frames = st.quiet.frames - 1
    st.quiet.ms = st.quiet.ms - (dtReal or 0) * 1000
  end
  if st.resumeIn then
    if st.resumeIn == 2 and st.jumpReload then
      st.jumpReload = nil
      st.quiet = nil
      local ms = objects.reloadCollisionIfDirty(clock)
      if ms > 0 then st.reloads = st.reloads + 1 end
      if st.watch then st.watch.rec.reloadMs = ms end
      -- the AI DecalRoads are clipped to the terrain, which exists only in the window: the AI map's nodes outside
      -- the window it was read with lie at z 0. Read it again here, hidden in the jump's pause (never on the fly:
      -- 2 s frozen at every window move, laptop run 4; control points instead of subdivisions crashed map.lua or,
      -- with that fixed, kept z 0 too and drove the AI a third as far, runs 5-7)
      if M.MAP_RESET_ON_JUMP and not st.aiDropped then
        local t0 = clock()
        local ok = pcall(function() map.reset() end)
        if st.watch then st.watch.rec.mapResetMs = clock() - t0 end
        log('I', 'ticino', string.format('AI map read again at the jump: %.1f ms%s', clock() - t0, ok and '' or ' (failed)'))
      end
      if M.DROP_AI_ROADS and not st.aiDropped then
        local ok, res = pcall(M.dropAIRoads)
        if ok and type(res) == 'string' and res:find('deleted', 1, true) then st.aiDropped = true end
        log('I', 'ticino', 'AI roads after the jump: ' .. tostring(res))
      end
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
  if st.lastXY and dtReal and dtReal > 0 then        -- the car's speed, smoothed over ~1 s
    local v = math.sqrt((x - st.lastXY[1]) ^ 2 + (y - st.lastXY[2]) ^ 2) / dtReal
    st.speed = (st.speed or v) + (v - (st.speed or v)) * math.min(1, dtReal)
  end
  st.lastXY = { x, y }
  local cfg = st.cfg
  local n = cfg.window / cfg.cell
  if M.HELPER then
    local lo, hi = followPlaces(n)
    helper.tick(x, y, st.window, lo, hi, n)
  end
  local cx, cy = cellOf(x, y)
  local wcx, wcy = st.window[1] / cfg.cell, st.window[2] / cfg.cell
  -- a jump: the first frame, or the car more than a tile out of its place in the window
  if st.started or cx - wcx < 1 or cx - wcx > n - 2 or cy - wcy < 1 or cy - wcy > n - 2 then
    st.started = nil
    st.act = 'jump'
    jump(x, y)
    return
  end
  cx, cy = cellHyst(x, y)
  if objects.updateCols(x, y) and not st.objRec then
    local c = objects.colCell and objects.colCell()
    st.objRec = { time = os.date('%H:%M:%S'), kind = 'colcell', wx = c and c[1], wy = c and c[2], objsQueued = 0 }
  end
  if not st.cell or st.cell[1] ~= cx or st.cell[2] ~= cy then
    st.act = 'retarget'
    st.cell = { cx, cy }
    local q = objects.retarget(cx, cy) + forest.retarget(cx, cy)
    st.objRec = { time = os.date('%H:%M:%S'), kind = 'tile', wx = cx, wy = cy, objsQueued = q, t0 = clock() }
    objects.updateFar(cx, cy, wcx, wcy, n)
    return            -- the window work waits for the next frame
  end
  -- the collision cells round the car (ProceduralMesh pieces, a few ms a frame)
  if objects.colsPending() then
    st.act = 'cols'
    objects.stepCols(clock, M.COL_BUDGET_MS)
    if objects.colsPending() then return end
  end
  -- the collision rebuild first, as soon as the cells and the colliders of the queue (it starts with them) are made
  -- and no terrain swap is too recent: the window's files and the drawn objects wait a frame. A rebuild only for props
  -- or trees waits (RELOAD_DEFER_MS at most) for the next one of the collision cells, which then takes them along.
  if objects.colDirty() then
    st.dirtySince = st.dirtySince or clock()
    local due = (objects.colUrgent and objects.colUrgent()) or clock() - st.dirtySince > M.RELOAD_DEFER_MS
    if due and not objects.colsPending() and not objects.collidersPending() and tryReload(st.objRec) then
      st.act = 'reload'
      st.objRec, st.dirtySince = nil, nil
      return
    end
  else
    st.dirtySince = nil
  end
  -- the near rings first (michi, 2026-10-29, "a onda"): the objects and trees of the car's tile and the ones beside it
  -- come before the next window's files (a window starts moving with the car still 2 tiles from its edge) and before
  -- anything farther
  if objects.nearPending(M.NEAR_RINGS) then
    st.act = 'near objects'
    objects.step(clock, M.OBJ_BUDGET_MS)
    return
  end
  if forest.nearPending() then
    st.act = 'near forest'
    forest.step(clock, M.FOREST_BUDGET_MS)
    return
  end
  if st.objRec and st.objRec.t0 and not st.objRec.nearMs then
    st.objRec.nearMs = clock() - st.objRec.t0
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
    st.act = 'window files'
    if runJob(st.job, M.BUDGET_MS) then
      local job = st.job
      st.job = nil
      if not job.failed then st.act = 'terrain swap'; apply(job, 'move') end
    end
    return            -- the objects wait for a frame without window work
  end
  -- the objects
  if M.BURST_EVERY_MS > 0 and (objects.pending() or forest.pending() or objects.farPending()) then
    local every = (st.speed or 0) < M.SLOW_MPS and M.BURST_EVERY_SLOW_MS or M.BURST_EVERY_MS
    if clock() - (st.lastBurst or -1e9) < every then st.act = 'wait burst'; return end
    st.lastBurst = clock()
    st.act = 'burst'
    local t0 = clock()
    objects.BURSTING = true
    -- the trees get their share of the burst (they waited for the whole object queue: PC test F1)
    local objMs = forest.pending() and M.BURST_MS * 0.6 or M.BURST_MS
    if objects.pending() then objects.step(clock, objMs) end
    objects.BURSTING = false
    local left = M.BURST_MS - (clock() - t0)
    if left > 0 and forest.pending() then forest.step(clock, 1000, nil, left) end
    left = M.BURST_MS - (clock() - t0)
    if left > 0 and objects.farPending() then objects.stepFar(clock, left) end
    return
  end
  if objects.pending() then
    st.act = 'objects'
    objects.step(clock, M.OBJ_BUDGET_MS)
    if objects.farPending() then objects.stepFar(clock, M.FAR_EVERY_MS) end
  elseif forest.pending() then
    st.act = 'forest'
    forest.step(clock, M.FOREST_BUDGET_MS)
  elseif st.objRec then
    perfLine(st.objRec)
    st.objRec = nil
  elseif not objects.farPending() then
    st.act = 'prefetch'
    if objects.prefetch(1) == 0 then forest.prefetch(cx, cy, 1) end
  else
    st.act = 'far'
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
           objects = s, forest = forest.stats(), last = st.perf[#st.perf], helper = helper.stats(), tcacheMisses = st.tcache.misses, bcacheMisses = st.bcache.misses }
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

-- the materials with dynamicCubemap: listed (nil), or turned off (false), with a fixed cubemap so metal still shines
function M.dynamicCubemaps(on)
  local names = {}
  for _, n in ipairs(scenetree.findClassObjects('Material') or {}) do
    local m = scenetree.findObject(n)
    local v = m and m:getField('dynamicCubemap', 0)
    if v == '1' or v == 'true' then
      names[#names + 1] = n
      if on == false then
        m:setField('dynamicCubemap', 0, '0')
        if (m:getField('cubemap', 0) or '') == '' then m:setField('cubemap', 0, 'global_cubemap_metalblurred') end
        if m.flush then pcall(function() m:flush() end) end
        if m.reload then pcall(function() m:reload() end) end
      end
    end
  end
  log('I', 'ticino', string.format('%d materials with dynamicCubemap%s: %s', #names,
    on == false and ' turned off' or '', table.concat(names, ', ')))
  return names
end

function M.setDynamic(on)
  local n = objects.setDynamic(on)
  log('I', 'ticino', string.format('%d streamed objects made %s', n, on and 'dynamic' or 'static'))
  return n
end

-- objects of the base scene by class, for a render test: ticino_stream.sceneCount()
function M.sceneCount()
  local out = {}
  for _, c in ipairs({ 'DecalRoad', 'SFXEmitter', 'WaterBlock', 'GroundCover', 'TSStatic', 'ProceduralMesh', 'Forest',
                       'SpawnSphere', 'BeamNGGameplayArea', 'BeamNGPointOfInterest' }) do
    out[c] = #(scenetree.findClassObjects(c) or {})
  end
  dump(out)
  return out
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
