-- Ticino: the level's shared object textures cooked at the start, before any streamed object binds them.
-- PC 2026-11-01 (server mode, cold cache): house walls kept the "IMPORTING TEXTURE" placeholder for 10 minutes. The log
-- had t_bld_plaster_b / t_bld_ashlar_b cooked without error, but no "reloadResource File changed" for them (it came
-- for plaster_nm and ashlar_ao): a material bound while its colour map was still being cooked kept the placeholder.
-- So every material of the level's own art (not the per-sign/prop plates, not the terrain) gets one small quad in front
-- of the camera for FRAMES frames as the level starts (warmup.lua's way), before the streamer makes objects.
local M = {}

M.FRAMES = 120            -- frames the quads stay (the cook of ~100 materials took ~40 s once on the PC, cold)
M.SKIP = { '/art/shapes/props/', '/art/shapes/signs/', '/art/terrains/' }
M.MAX = 400

local S

local function skip(p)
  for _, s in ipairs(M.SKIP) do if p:find(s, 1, true) then return true end end
  return false
end

-- the names of the level's materials with a PNG map
function M.list(level)
  local out, files = {}, {}
  pcall(function() files = FS:findFiles('/levels/' .. level .. '/art/', '*.materials.json', -1, true, false) or {} end)
  for _, f in ipairs(files) do
    if not skip(f) then
      local ok, d = pcall(jsonReadFile, f)
      if ok and type(d) == 'table' then
        for name, m in pairs(d) do
          if type(m) == 'table' and m.class == 'Material' then
            local png = false
            for _, st in ipairs(type(m.Stages) == 'table' and m.Stages or {}) do
              for _, v in pairs(st) do
                if type(v) == 'string' and v:lower():sub(-4) == '.png' then png = true end
              end
            end
            if png and #out < M.MAX then out[#out + 1] = name end
          end
        end
      end
    end
  end
  table.sort(out)
  return out
end

local function place()
  local p, fwd = core_camera.getPosition(), core_camera.getForward()
  fwd = vec3(fwd.x, fwd.y, fwd.z):normalized()
  local right = fwd:cross(vec3(0, 0, 1)):normalized()
  local up = right:cross(fwd):normalized()
  local cols, step = 20, 0.25
  local rows = math.ceil(#S.ids / cols)
  for k, id in ipairs(S.ids) do
    local o = scenetree.findObjectById(id)
    if o then
      local c, r = (k - 1) % cols, math.floor((k - 1) / cols)
      o:setPosition(p + fwd * 6 + right * ((c - cols / 2) * step) + up * ((r - rows / 2) * step))
    end
  end
end

-- one small double-sided quad of material name (its id, or nil)
local function quad(objName, name, s)
  local ok, id = pcall(function()
    local o = createObject('ProceduralMesh')
    o:registerObject(objName)
    o.canSave = false
    local v = { { x = -s, y = 0, z = -s }, { x = s, y = 0, z = -s }, { x = s, y = 0, z = s }, { x = -s, y = 0, z = s } }
    local fv = {}
    for i = 1, 4 do fv[i] = { v = i - 1, n = 0, u = i - 1 } end
    o:createMesh({ { { verts = v, normals = { { x = 0, y = -1, z = 0 } },
      uvs = { { u = 0, v = 1 }, { u = 1, v = 1 }, { u = 1, v = 0 }, { u = 0, v = 0 } },
      faces = { fv[1], fv[2], fv[3], fv[1], fv[3], fv[4], fv[1], fv[3], fv[2], fv[1], fv[4], fv[3] },
      material = name } } })
    return o:getID()
  end)
  return ok and id or nil
end

function M.start(level)
  M.clear()
  local mats = M.list(level)
  S = { ids = {}, frames = 0, failed = 0, n = #mats }
  for k, name in ipairs(mats) do
    local id = quad('ticino_texwarm_' .. k, name, 0.1)
    if id then S.ids[#S.ids + 1] = id else S.failed = S.failed + 1 end
  end
  log('I', 'ticino', string.format('texture warm-up: %d materials of the level art, %d quads (%d failed)', #mats,
    #S.ids, S.failed))
  if #S.ids == 0 then S = nil end
end

-- each frame while it runs (true: still running)
function M.step()
  if not S then return false end
  pcall(place)
  S.frames = S.frames + 1
  if S.frames < M.FRAMES then return true end
  log('I', 'ticino', string.format('texture warm-up done: %d quads for %d frames', #S.ids, S.frames))
  M.clear()
  return false
end

function M.clear()
  if not S then return end
  for _, id in ipairs(S.ids) do
    local o = scenetree.findObjectById(id)
    if o then o:delete() end
  end
  S = nil
end

function M.running() return S ~= nil end

-- ---- Rolling warm-up of the sign plates while driving (PC flight j_A 2026-11-01, 76c3d7e, warm cache: the first spawn
-- of direction_signs.cdae took 195 ms and of props_signs 230 ms in zone ti_0_1, one frame each: a shape lists 45-77
-- sign materials, each with a PNG of its own, all loaded in the frame the shape comes). A shape whose path matches
-- ROLL_PATTERNS is held in the objects queue (objects.warmReady) until the sign materials it names (warmup_mats.json,
-- read from the material list at the end of the .cdae) have each been drawn on a tiny quad at the camera, ROLL_PER_FRAME
-- new materials a frame, for ROLL_FRAMES frames; never longer than ROLL_WAIT_MS. Settings "signWarm".
M.ROLL = true
M.ROLL_PATTERNS = { '/signs/', 'props_sign', 'fuel' }
M.ROLL_PER_FRAME = 3
M.ROLL_FRAMES = 3
M.ROLL_WAIT_MS = 6000
M.ROLL_TAIL = 131072        -- bytes at the end of a .cdae read for its material names
M.ROLL_SIZE = 0.002         -- half size of a quad (m), ROLL_DIST in front of the camera: a pixel or two
M.ROLL_DIST = 0.5

local R

function M.rollInit(level)
  R = { set = {}, warm = {}, shapes = {}, queue = {}, qpos = 1, live = {}, n = 0,
        stats = { shapes = 0, mats = 0, made = 0, failed = 0, timeouts = 0, scanMs = 0 } }
  local ok, s = pcall(readFile, '/levels/' .. level .. '/warmup_mats.json')
  local ok2, list = false, nil
  if ok and s then ok2, list = pcall(jsonDecode, s) end
  local n = 0
  for _, m in ipairs(ok2 and type(list) == 'table' and list or {}) do R.set[m] = true; n = n + 1 end
  if n == 0 then R = nil end
  log('I', 'ticino', string.format('sign warm-up while driving: %s (%d sign materials)', R and 'on' or 'off', n))
end

local function rollMatch(shape)
  for _, p in ipairs(M.ROLL_PATTERNS) do if shape:find(p, 1, true) then return true end end
  return false
end

local function scan(shape, clock)
  local t0 = clock()
  local mats = {}
  local ok, data = pcall(readFile, shape)
  if ok and type(data) == 'string' then
    local seen = {}
    for w in data:sub(-M.ROLL_TAIL):gmatch('[%w_]+') do
      if R.set[w] and not seen[w] then seen[w] = true; mats[#mats + 1] = w end
    end
  end
  R.stats.scanMs = R.stats.scanMs + clock() - t0
  return mats
end

-- may objects.lua spawn this shape now? (true: no sign plates to warm, warmed, or waited ROLL_WAIT_MS)
function M.shapeReady(shape, clock)
  if not R or type(shape) ~= 'string' then return true end
  local s = R.shapes[shape]
  if s == nil then
    if not rollMatch(shape) then R.shapes[shape] = false return true end
    local mats = scan(shape, clock)
    local todo = 0
    for _, m in ipairs(mats) do
      if not R.warm[m] then
        todo = todo + 1
        if R.warm[m] == nil then R.warm[m] = false; R.queue[#R.queue + 1] = m end
      end
    end
    s = { mats = mats, t0 = clock(), done = todo == 0 }
    R.shapes[shape] = s
    R.stats.shapes = R.stats.shapes + 1
  end
  if not s or s.done then return true end
  for _, m in ipairs(s.mats) do
    if not R.warm[m] then
      if clock() - s.t0 > M.ROLL_WAIT_MS then
        s.done = true
        R.stats.timeouts = R.stats.timeouts + 1
        log('W', 'ticino', 'sign warm-up: waited too long for ' .. shape)
        return true
      end
      return false
    end
  end
  s.done = true
  return true
end

-- each frame: new quads for the queued materials, the old ones aged and deleted. Returns the quads made now.
function M.roll()
  if not R then return 0 end
  local made = 0
  for i = #R.live, 1, -1 do
    local l = R.live[i]
    l.frames = l.frames + 1
    if l.frames >= M.ROLL_FRAMES then
      local o = scenetree.findObjectById(l.id)
      if o then o:delete() end
      R.warm[l.mat] = true
      table.remove(R.live, i)
    end
  end
  while made < M.ROLL_PER_FRAME and R.qpos <= #R.queue do
    local m = R.queue[R.qpos]
    R.qpos = R.qpos + 1
    if not R.warm[m] then
      R.n = R.n + 1
      local id = quad('ticino_signwarm_' .. R.n, m, M.ROLL_SIZE)
      if id then
        R.live[#R.live + 1] = { id = id, mat = m, frames = 0 }
        R.stats.made = R.stats.made + 1
        made = made + 1
      else
        R.warm[m] = true                    -- no quad (no ProceduralMesh?): never hold a shape for it
        R.stats.failed = R.stats.failed + 1
      end
      R.stats.mats = R.stats.mats + 1
    end
  end
  if made > 0 then R.busy = true end
  if R.qpos > #R.queue and #R.queue > 0 then R.queue, R.qpos = {}, 1 end
  if R.busy and #R.live == 0 and #R.queue == 0 then
    R.busy = false
    local t = R.stats
    log('I', 'ticino', string.format('sign warm-up: %d materials of %d shapes warmed so far (%d failed, %d waits too long, '
      .. 'scans %.0f ms)', t.made, t.shapes, t.failed, t.timeouts, t.scanMs))
  end
  if #R.live > 0 then
    pcall(function()
      local p, fwd = core_camera.getPosition(), core_camera.getForward()
      local at = p + vec3(fwd.x, fwd.y, fwd.z):normalized() * M.ROLL_DIST
      for _, l in ipairs(R.live) do
        local o = scenetree.findObjectById(l.id)
        if o then o:setPosition(at) end
      end
    end)
  end
  return made
end

function M.rollStats() return R and R.stats end

function M.rollClear()
  if not R then return end
  for _, l in ipairs(R.live) do
    local o = scenetree.findObjectById(l.id)
    if o then o:delete() end
  end
  R = nil
end

return M
