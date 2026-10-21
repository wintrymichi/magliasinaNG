-- In-game test of magliaso_pura v3.0.40 (BeamNG.drive 0.40): frame rate at fixed places, the README screenshots,
-- the game's traffic. Copy to <user>/lua/ge/extensions/magliaso/v3040.lua and start the game with
--   Bin64\BeamNG.drive.x64.exe -level magliaso_pura/main.level.json -onLevelLoad_ext magliaso_v3040
-- Reads <user>/magliaso_v3040/plan.json (written by make_plan.py), {"phases": [...], "fps": [...], "shots": [...],
-- "traffic": {...}, "quit": true}. Writes to <user>/magliaso_v3040/: results.json (frame rate per place, the shots
-- taken and how each camera was placed, the traffic samples), shots/<name>.png, done.txt; log lines "magliaso_v3040".
-- Remove the extension after the test: a left-over extension runs on every level.
local M = {}
local OUT = 'magliaso_v3040/'
local started = false
local frames, frameTime = 0, 0
local res = {fps = {}, shots = {}, traffic = {}, notes = {}}

local function note(s)
  res.notes[#res.notes + 1] = s
  log('I', 'magliaso_v3040', s)
end

local function save()
  jsonWriteFile(OUT .. 'results.json', res, true)
end

local function terrainZ(x, y)
  local ok, h = pcall(function() return core_terrain.getTerrainHeight(vec3(x, y, 0)) end)
  if ok and h then return h end
  return 0
end

local function surfaceZ(x, y, from)
  -- the game's surface (terrain, roads, bridges) under a point, cast down from `from` (absolute) or high above
  local ok, h = pcall(function() return be:getSurfaceHeightBelow(vec3(x, y, from or 3000)) end)
  if ok and h and h > -1000 then return h end
  return terrainZ(x, y)
end

local function los(a, b)
  -- free distance from a towards b (castRayStatic: the first static object or terrain hit); nil if unknown
  local d = b - a
  local L = d:length()
  local ok, hit = pcall(function() return castRayStatic(a, d:normalized(), L) end)
  if ok and type(hit) == 'number' then return hit, L end
  return nil, L
end

local function setCam(pos, target, fov)
  commands.setFreeCamera()
  local dir = (target - pos):normalized()
  local ok = pcall(function()
    local q = quatFromDir(dir, vec3(0, 0, 1))
    core_camera.setPosRot(0, pos.x, pos.y, pos.z, q.x, q.y, q.z, q.w)
  end)
  if not ok then
    local yaw = math.deg(math.atan2(dir.x, dir.y)) % 360
    local pitch = math.deg(math.asin(math.max(-1, math.min(1, dir.z))))
    core_camera.setPosition(0, pos)
    core_camera.setFreeCameraYawPitchRollDeg(yaw, -pitch, 0)
  end
  if fov then pcall(function() core_camera.setFOV(0, fov) end) end
end

local function shoot(name)
  local path = OUT .. 'shots/' .. name
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

local function graph()
  local ok = pcall(function() map.assureLoad() end)
  local m = map.getMap()
  return m and m.nodes or {}
end

local function roadLook(v)
  -- a camera on a node of the game's AI roads between rmin and rmax from the target, eye m over the road, with a
  -- free line of sight to the target, as close as possible to `ideal` m from it
  local nodes = graph()
  local tz = v.target[3] or (terrainZ(v.target[1], v.target[2]) + (v.target_dz or 0))
  local T = vec3(v.target[1], v.target[2], tz)
  local best, bestScore, tried = nil, math.huge, 0
  for id, node in pairs(nodes) do
    local p = node.pos
    local d = math.sqrt((p.x - T.x) ^ 2 + (p.y - T.y) ^ 2)
    if d >= v.rmin and d <= v.rmax then
      tried = tried + 1
      local C = vec3(p.x, p.y, p.z + (v.eye or 1.6))
      local free, L = los(C, T)
      local clear = free == nil or free >= L - (v.clear or 4.0)
      local score = math.abs(d - (v.ideal or (v.rmin + v.rmax) / 2)) + (clear and 0 or 1e6)
      if score < bestScore then best, bestScore = {C = C, clear = clear, free = free, L = L, node = id}, score end
    end
  end
  return best, T, tried
end

local function snapRoad(x, y, lookX, lookY)
  -- the closest point on the game's AI roads, the direction along the road towards (lookX, lookY), its half width
  local n1, n2 = map.findClosestRoad(vec3(x, y, surfaceZ(x, y)))
  local nodes = graph()
  local a, b = nodes[n1].pos, nodes[n2].pos
  local ab = b - a
  local t = math.max(0, math.min(1, ((x - a.x) * ab.x + (y - a.y) * ab.y) / (ab.x * ab.x + ab.y * ab.y)))
  local px, py = a.x + ab.x * t, a.y + ab.y * t
  local d = vec3(ab.x, ab.y, 0):normalized()
  if d.x * (lookX - px) + d.y * (lookY - py) < 0 then d = -d end
  local hw = math.min(nodes[n1].radius or 3, nodes[n2].radius or 3)
  return px, py, d, hw, n1, n2
end

local function player()
  return be:getPlayerVehicle(0)
end

local function ensureCar(model)
  local veh = player()
  if veh and veh.jbeam == model then return veh end
  local ok, err = pcall(function() core_vehicles.replaceVehicle(model, {}) end)
  if not ok then note('replaceVehicle failed: ' .. tostring(err)) end
  return nil
end

local function placeCar(v)
  -- the player's car in the right-hand lane of the road at v.at, facing v.look (or at v.pos / v.rot as given)
  local veh = player()
  if not veh then return nil end
  local pos, q, info
  if v.pos and v.rot then
    pos = vec3(v.pos[1], v.pos[2], surfaceZ(v.pos[1], v.pos[2], v.pos[3] + 3) + 0.4)
    q = quat(v.rot[1], v.rot[2], v.rot[3], v.rot[4])
    info = 'given'
  else
    local px, py, d, hw = snapRoad(v.at[1], v.at[2], v.look[1], v.look[2])
    local right = vec3(d.y, -d.x, 0)
    local off = math.min(hw * 0.5, 1.9) * (v.lane or 1)
    px, py = px + right.x * off, py + right.y * off
    pos = vec3(px, py, surfaceZ(px, py) + 0.4)
    q = quatFromDir(-d, vec3(0, 0, 1))          -- the car's front is its -Y
    info = string.format('road half width %.1f, lane offset %.1f', hw, off)
  end
  veh:setPositionRotation(pos.x, pos.y, pos.z, q.x, q.y, q.z, q.w)
  return pos, info
end

local function setTod(t)
  local ok, err = pcall(function()
    local tod = core_environment.getTimeOfDay()
    tod.time = t
    tod.play = false
    core_environment.setTimeOfDay(tod)
  end)
  if not ok then note('time of day failed: ' .. tostring(err)) end
end

local function measureFps(job, places, seconds, warm)
  for _, p in ipairs(places) do          -- warm-up pass: load what each place shows
    setCam(vec3(p.cam[1], p.cam[2], p.cam[3]), vec3(p.target[1], p.target[2], p.target[3]), p.fov)
    job.sleep(warm)
  end
  for _, p in ipairs(places) do
    setCam(vec3(p.cam[1], p.cam[2], p.cam[3]), vec3(p.target[1], p.target[2], p.target[3]), p.fov)
    job.sleep(3.0)
    frames, frameTime = 0, 0
    job.sleep(seconds)
    local fps = frameTime > 0 and frames / frameTime or 0
    res.fps[#res.fps + 1] = {name = p.name, fps = math.floor(fps * 10 + 0.5) / 10, frames = frames, seconds = frameTime}
    note(string.format('FPS %s %.1f', p.name, fps))
    save()
  end
end

local function takeShots(job, shots, plan)
  local tod0 = nil
  pcall(function() tod0 = core_environment.getTimeOfDay().time end)
  for _, v in ipairs(shots) do
    local rec = {name = v.name, kind = v.kind}
    local ok, err = pcall(function()
      if v.tod then setTod(v.tod) elseif tod0 then setTod(tod0) end
      if v.kind == 'free' then
        local tz = v.target[3] or (terrainZ(v.target[1], v.target[2]) + (v.target_dz or 0))
        local cz = v.cam[3] or (terrainZ(v.cam[1], v.cam[2]) + (v.cam_dz or 2))
        setCam(vec3(v.cam[1], v.cam[2], cz), vec3(v.target[1], v.target[2], tz), v.fov)
        rec.cam = {v.cam[1], v.cam[2], cz}
      elseif v.kind == 'road_look' then
        local best, T, tried = roadLook(v)
        rec.tried = tried
        if not best then error('no road node in range') end
        setCam(best.C, T, v.fov)
        rec.cam = {best.C.x, best.C.y, best.C.z}
        rec.clear, rec.free, rec.dist = best.clear, best.free, best.L
      elseif v.kind == 'car' then
        local veh = player()
        if not veh or veh.jbeam ~= (v.model or 'etk800') then
          ensureCar(v.model or 'etk800')
          job.sleep(8.0)
        end
        local pos, info = placeCar(v)
        rec.cam = pos and {pos.x, pos.y, pos.z}
        rec.info = info
        job.sleep(2.0)
        core_camera.setByName(0, v.camera or 'driver')
        if v.camera == 'orbit' then pcall(function() core_camera.resetCamera(0) end) end
        if v.fov then pcall(function() core_camera.setFOV(0, v.fov) end) end
      end
    end)
    if not ok then
      rec.error = tostring(err)
      note('shot ' .. v.name .. ' failed: ' .. tostring(err))
    else
      job.sleep(v.wait or plan.wait or 20.0)   -- let streaming, LOD, the forest and the textures settle
      rec.method = shoot(v.name)
      job.sleep(2.0)
      note('shot ' .. v.name .. ' ' .. tostring(rec.method))
    end
    res.shots[#res.shots + 1] = rec
    save()
  end
  if tod0 then setTod(tod0) end
end

local function trafficTest(job, t)
  local tr = {spawned = {}, samples = {}}
  res.traffic = tr
  if t.at then
    ensureCar('etk800')
    job.sleep(8.0)
    placeCar(t.at)
    job.sleep(2.0)
  end
  local ok, err
  if (t.parked or 0) > 0 and gameplay_parking then
    ok, err = pcall(gameplay_parking.setupVehicles, t.parked)
    tr.parking = ok and 'ok' or tostring(err)
  else
    tr.parking = gameplay_parking and 'skipped' or 'no gameplay_parking'
  end
  if gameplay_traffic then
    ok, err = pcall(gameplay_traffic.setupTraffic, t.cars or 12)
    tr.setup = ok and 'ok' or tostring(err)
  else
    tr.setup = 'no gameplay_traffic'
  end
  note('traffic setup: ' .. tostring(tr.setup) .. ', parking: ' .. tostring(tr.parking))
  job.sleep(t.settle or 30.0)
  if t.shot then
    pcall(function() core_camera.setByName(0, 'orbit'); core_camera.resetCamera(0) end)
    job.sleep(10.0)
    tr.shot = shoot(t.shot)
  end
  local elapsed = 0
  while elapsed < (t.duration or 300) do
    local rows = {}
    local data = gameplay_traffic and gameplay_traffic.getTrafficData and gameplay_traffic.getTrafficData() or {}
    for id, d in pairs(data) do
      local obj = be:getObjectByID(id)
      if obj then
        local p, vel = obj:getPosition(), obj:getVelocity()
        local road = {map.findClosestRoad(p)}
        rows[#rows + 1] = {id = id, x = p.x, y = p.y, z = p.z, v = vel:length(), a = road[1], b = road[2], d = road[3],
                           state = type(d) == 'table' and d.state or nil, model = obj.jbeam}
      end
    end
    tr.samples[#tr.samples + 1] = {t = elapsed, cars = rows}
    if #tr.samples % 15 == 0 then save() end
    job.sleep(t.every or 2.0)
    elapsed = elapsed + (t.every or 2.0)
  end
  local parked = 0
  pcall(function()
    for _, _ in pairs(gameplay_parking.getParkedCarsList() or {}) do parked = parked + 1 end
  end)
  tr.parked_cars = parked
  save()
end

local function run()
  if started then return end
  started = true
  local plan = jsonReadFile(OUT .. 'plan.json') or {}
  if not FS:directoryExists(OUT .. 'shots') then FS:directoryCreate(OUT .. 'shots', true) end
  core_jobsystem.create(function(job)
    job.sleep(plan.start_wait or 60.0)        -- the textures of the first view
    if extensions.ui_visibility then pcall(extensions.ui_visibility.setCef, false) end   -- no HUD in the shots
    for _, phase in ipairs(plan.phases or {}) do
      local ok, err = pcall(function()
        if phase == 'fps' then
          local veh = player()
          if veh then veh:setPositionRotation(0, 0, -500, 0, 0, 0, 1) end   -- no car in the frame-rate views
          measureFps(job, plan.fps or {}, plan.fps_seconds or 5.0, plan.fps_warm or 8.0)
        elseif phase == 'shots' then
          takeShots(job, plan.shots or {}, plan)
        elseif phase == 'traffic' then
          trafficTest(job, plan.traffic or {})
        end
      end)
      if not ok then note('phase ' .. phase .. ' failed: ' .. tostring(err)) end
      save()
    end
    if extensions.ui_visibility then pcall(extensions.ui_visibility.setCef, true) end
    writeFile(OUT .. 'done.txt', 'done')
    note('DONE')
    save()
    if plan.quit then shutdown(0) end
  end)
end

M.onUpdate = function(dtReal)
  frames = frames + 1
  frameTime = frameTime + (dtReal or 0)
end
M.onClientPostStartMission = function() run() end
M.onWorldReadyState = function(state) if state == 2 then run() end end
return M
