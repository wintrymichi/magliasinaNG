-- Phase 0 in-game test of the Ticino streaming (beamng/ticino), for BeamNG.drive 0.40. Runs the same plan in the
-- level `ticino` and, for the comparison, in `magliaso_pura` (v3.1.1). Copy to <user>/lua/ge/extensions/ticino/autotest.lua
-- (extension ticino_autotest) and start the game with run_test.ps1, which passes
--   -level <level>/main.level.json -onLevelLoad_ext ticino_autotest
-- Writes to <user>/ticino_test/: results.json (notes, the drive's samples, the hitches, the jumps), shots/*.png,
-- done.txt. The streaming itself logs every window move to <user>/ticino_perf.csv. Remove the extension afterwards:
-- a left-over extension runs in every level.
local M = {}
local OUT = 'ticino_test/'
local started = false
local res = {notes = {}, drive = {}, hitches = {}, jumps = {}, shots = {}}
local frameLog = nil            -- set while a phase records frame times
local worst = 0

-- the plan: places in level coordinates (both levels share them)
local PLAN = {
  start_wait = 60,              -- textures of the first view
  fps_cap = 30,                 -- michi: 30 fps in tests that do not measure FPS (a hitch shows at any cap)
  drive_minutes = 4,            -- the AI drives the player's car through the traffic network, per variant
  variants = {                  -- collision settings of the streaming (level ticino only), one drive each
    {name = 'all_collide', radius = 1, off = {}},
    {name = 'skin_no_collision', radius = 1, off = {'level_objects/terrain_skin'}},
  },
  jumps = {                     -- teleports far away: the streaming pauses and builds the window at once
    {name = 'nord', at = {2290, 5649}},
    {name = 'ovest', at = {-3921, 2303}},
    {name = 'ponte_tresa', at = {-2250, -1060}},
    {name = 'magliaso', at = {783, -1143}},
  },
}

local function note(s)
  res.notes[#res.notes + 1] = string.format('%.1f %s', os.clock(), s)
  log('I', 'ticino_autotest', s)
end

local function save() jsonWriteFile(OUT .. 'results.json', res, true) end

local function player() return be:getPlayerVehicle(0) end

local function level()
  local p = getMissionFilename and getMissionFilename() or ''
  return p:match('/levels/([^/]+)/') or p
end

local function streamStatus()
  if not ticino_stream or not ticino_stream.status then return nil end
  local ok, s = pcall(ticino_stream.status)
  return ok and s or nil
end

local function terrainZ(x, y)
  local ok, h = pcall(function() return core_terrain.getTerrainHeight(vec3(x, y, 0)) end)
  return ok and h or nil
end

local function shoot(name)
  local path = OUT .. 'shots/' .. level() .. '_' .. name
  if type(createScreenshot2) == 'function' then
    if pcall(createScreenshot2, {filename = path, writeJPG = false, superSampling = 1}) then return 'createScreenshot2' end
  end
  if screenshot and type(screenshot.doScreenshot) == 'function' then
    if pcall(screenshot.doScreenshot, nil, nil, path, 'png') then return 'doScreenshot' end
  end
  if type(createScreenshot) == 'function' then
    if pcall(createScreenshot, path, 'png') then return 'createScreenshot' end
  end
  return nil
end

local function placeOnRoad(x, y)
  -- the player's car on the AI road nearest (x, y), along it, 0.5 m over the surface
  local veh = player()
  if not veh then return nil, 'no car' end
  pcall(function() map.assureLoad() end)
  local n1, n2 = map.findClosestRoad(vec3(x, y, 1000))
  if not n1 then return nil, 'no road' end
  local nodes = map.getMap().nodes
  local a, b = nodes[n1].pos, nodes[n2].pos
  local d = vec3(b.x - a.x, b.y - a.y, 0):normalized()
  local p = vec3(a.x, a.y, a.z + 0.5)
  local q = quatFromDir(-d, vec3(0, 0, 1))          -- the car's front is its -Y
  veh:setPositionRotation(p.x, p.y, p.z, q.x, q.y, q.z, q.w)
  return p
end

-- 'span' drives on through the whole road network; 'traffic' stopped for good after 90 m in the first test (2026-10-26)
local function aiDrive(on, mode)
  local veh = player()
  if not veh then return end
  if on then
    veh:queueLuaCommand('ai.setMode("' .. (mode or 'span') .. '") ai.setSpeedMode("legal") ai.setAggression(0.4) ai.driveInLane("on")')
  else
    veh:queueLuaCommand('ai.setMode("disabled")')
  end
end

local function sample(t)
  local veh = player()
  if not veh then return end
  local p, v = veh:getPosition(), veh:getVelocity()
  local tz = terrainZ(p.x, p.y)
  local s = {t = t, x = p.x, y = p.y, z = p.z, v = v:length(), terrain = tz, worst_ms = math.floor(worst * 1000)}
  -- under the terrain by more than 3 m: the car fell through the ground (or a tunnel/underpass: check the place)
  if tz and p.z < tz - 3 then s.below = true; note(string.format('car %.1f m under the terrain at %.0f,%.0f', tz - p.z, p.x, p.y)) end
  local st = streamStatus()
  if st then s.stream = st end
  res.drive[#res.drive + 1] = s
  worst = 0
end

local function run()
  if started then return end
  started = true
  if not FS:directoryExists(OUT .. 'shots') then FS:directoryCreate(OUT .. 'shots', true) end
  note('level ' .. level() .. ', ticino_stream ' .. (ticino_stream and 'loaded' or 'NOT loaded'))
  pcall(function()
    settings.setValue('FPSLimiterEnabled', true)
    settings.setValue('FPSLimiter', PLAN.fps_cap)
  end)
  core_jobsystem.create(function(job)
    job.sleep(PLAN.start_wait)
    if extensions.ui_visibility then pcall(extensions.ui_visibility.setCef, false) end
    if not player() then
      pcall(function() core_vehicles.spawnNewVehicle('etk800', {}) end)
      job.sleep(10)
    end
    local veh = player()
    if veh then
      local p = veh:getPosition()
      note(string.format('car at %.0f,%.0f,%.1f, terrain %s', p.x, p.y, p.z, tostring(terrainZ(p.x, p.y))))
    else
      note('no player car')
    end
    pcall(function() core_camera.setByName(0, 'orbit'); core_camera.resetCamera(0) end)
    job.sleep(5)
    res.shots[#res.shots + 1] = {name = 'spawn', method = shoot('spawn')}
    save()

    -- collision rebuild standing still: all, skin off, all again (warm), skin off again; ticino_perf.csv has each
    if ticino_stream and ticino_stream.setCollision then
      for k, off in ipairs({{}, {'level_objects/terrain_skin'}, {}, {'level_objects/terrain_skin'}}) do
        local q = ticino_stream.setCollision(1, off)
        note(string.format('reload test %d (%s) at %s: %s objects requeued', k, #off > 0 and 'skin off' or 'all',
          os.date('%H:%M:%S'), tostring(q)))
        job.sleep(12)
      end
    end

    -- the drives: the AI takes the car through the network, one sample a second, once per collision variant
    frameLog = true
    local variants = (ticino_stream and ticino_stream.setCollision) and PLAN.variants or {{name = 'level'}}
    local t = 0
    for _, v in ipairs(variants) do
      if v.radius then
        local q = ticino_stream.setCollision(v.radius, v.off)
        note(string.format('variant %s from %s (os %s): %s objects requeued', v.name, os.date('%H:%M:%S'), os.clock(), tostring(q)))
      end
      res.drive[#res.drive + 1] = {variant = v.name, time = os.date('%H:%M:%S')}
      job.sleep(10)
      aiDrive(true)
      local still, modes, m = 0, {'span', 'random', 'span'}, 1
      for i = 1, PLAN.drive_minutes * 60 do
        job.sleep(1)
        t = t + 1
        sample(t)
        -- a stuck AI: give it the next mode, then put the car on the road 30 m on
        local last = res.drive[#res.drive]
        still = (last and last.v and last.v < 1) and still + 1 or 0
        if still == 15 then
          m = m % #modes + 1
          note('AI stuck at ' .. t .. ' s: mode ' .. modes[m])
          aiDrive(true, modes[m])
        elseif still == 30 then
          local veh = player()
          if veh then
            local p = veh:getPosition()
            local d = veh:getDirectionVector()
            note('AI still stuck: car moved 30 m on')
            placeOnRoad(p.x + d.x * 30, p.y + d.y * 30)
            job.sleep(3)
            aiDrive(true, modes[m])
          end
          still = 0
        end
        if i % 30 == 0 then save() end
        if i % 120 == 0 then res.shots[#res.shots + 1] = {name = v.name .. '_' .. i, method = shoot(v.name .. '_' .. i)} end
      end
      aiDrive(false)
      note('drive ' .. v.name .. ' done')
      save()
    end

    -- the jumps
    for _, j in ipairs(PLAN.jumps) do
      worst = 0
      local p, err = placeOnRoad(j.at[1], j.at[2])
      local rec = {name = j.name, at = j.at, placed = p and {p.x, p.y, p.z} or err}
      job.sleep(15)                          -- the window, the objects near, the textures
      local veh = player()
      if veh then
        local q = veh:getPosition()
        rec.car = {q.x, q.y, q.z}
        rec.terrain = terrainZ(q.x, q.y)
        rec.fell = rec.terrain and q.z < rec.terrain - 3 or false
      end
      rec.worst_ms = math.floor(worst * 1000)
      rec.stream = streamStatus()
      pcall(function() core_camera.setByName(0, 'orbit'); core_camera.resetCamera(0) end)
      job.sleep(5)
      rec.shot = shoot('jump_' .. j.name)
      res.jumps[#res.jumps + 1] = rec
      note(string.format('jump %s: worst frame %d ms, fell %s', j.name, rec.worst_ms, tostring(rec.fell)))
      save()
    end
    frameLog = nil
    if extensions.ui_visibility then pcall(extensions.ui_visibility.setCef, true) end
    writeFile(OUT .. 'done.txt', 'done')
    note('DONE')
    save()
    shutdown(0)
  end)
end

M.onUpdate = function(dtReal)
  if frameLog and dtReal then
    if dtReal > worst then worst = dtReal end
    if dtReal > 0.1 then                    -- frames over 100 ms, with what the streaming was doing
      local veh = player()
      local p = veh and veh:getPosition()
      res.hitches[#res.hitches + 1] = {ms = math.floor(dtReal * 1000), x = p and p.x, y = p and p.y}
    end
  end
end
M.onClientPostStartMission = function() run() end
M.onWorldReadyState = function(state) if state == 2 then run() end end
return M
