-- Trailer footage of the magliaso_pura level (v3), rendered frame by frame inside the game.
-- Installed as <user>/lua/ge/extensions/magliaso/trailer.lua (the extension name's "_" is a folder) and loaded with
--   BeamNG.drive.x64 -level magliaso_pura -onLevelLoad_ext magliaso_trailer
-- Reads <user>/magliaso_trailer_shots.json (beamng/trailer/shots.py). For every shot it places the free
-- camera (or the game's orbit camera for gameplay shots) and saves each frame to
-- <user>/screenshots/magliaso_trailer/<shot>/<nnnnn>.png with its time in <shot>/frames.csv, then quits.
-- Frames are not tied to the game's frame rate: camera moves run on a virtual clock that advances exactly
-- 1/fps per saved frame; shots with cars run the physics continuously at 2 % speed and save a frame each time
-- the simulation passes the next 1/fps mark, with its exact simulation time (trailer/edit.py picks by time).
-- The window is switched to borderless at the frame size first (the game saves that into settings.json:
-- put the user's settings back after the shoot).
-- Scout mode saves one still at the first, middle and last moment of every shot instead.
-- Temporary: remove it from the game folders after the capture.
local M = {}
local started = false
local ROOT = 'screenshots/magliaso_trailer'
local simT, lastReal = 0, 1 / 60
local frameNo = 0                                         -- rendered frames (onUpdate), for waitFrames

-- job.yield() may resume within the same frame: wait for k frames really rendered
local function waitFrames(job, k)
  local f0 = frameNo
  repeat job.sleep(0.001) until frameNo >= f0 + (k or 1)
end

local function ground(x, y)
  local ok, h = pcall(function() return be:getSurfaceHeightBelow(vec3(x, y, 3000)) end)
  if ok and h and h > -1000 then return h end
  return core_terrain.getTerrainHeight(vec3(x, y, 0)) or 0
end

local function look(cam, tgt, fov, roll)
  local dx, dy, dz = tgt.x - cam.x, tgt.y - cam.y, tgt.z - cam.z
  local yaw = math.deg(math.atan2(dx, dy)) % 360
  local pitch = math.deg(math.atan2(dz, math.sqrt(dx * dx + dy * dy)))
  core_camera.setPosition(0, cam)
  core_camera.setFreeCameraYawPitchRollDeg(yaw, -pitch, roll or 0)
  if fov then core_camera.setFOV(0, fov) end
end

local function setTod(t)
  if t and core_environment and core_environment.setTimeOfDay then
    pcall(function() core_environment.setTimeOfDay({time = t, play = false}) end)
  end
end

local function pausePhysics(p)
  if not pcall(function() simTimeAuthority.pause(p) end) then pcall(function() be:setPhysicsRunning(not p) end) end
end

local function smooth(t) return t * t * (3 - 2 * t) end   -- ease in and out

-- centripetal Catmull-Rom through points P (vec3), u in [0,1] over the whole curve
local function catmull(P, u)
  local n = #P
  if n == 1 then return P[1] end
  local seg = math.min(n - 1, math.floor(u * (n - 1)) + 1)
  local t = u * (n - 1) - (seg - 1)
  local p0, p1, p2, p3 = P[math.max(1, seg - 1)], P[seg], P[seg + 1], P[math.min(n, seg + 2)]
  local t2, t3 = t * t, t * t * t
  return (p1 * 2 + (p2 - p0) * t + (p0 * 2 - p1 * 5 + p2 * 4 - p3) * t2 + (p1 * 3 - p0 - p2 * 3 + p3) * t3) * 0.5
end

-- the closest AI road at (x, y): point on it, unit direction, its two nodes
local function snapRoad(x, y)
  local n1, n2 = map.findClosestRoad(vec3(x, y, ground(x, y)))
  if not n1 then return nil end
  local m = map.getMap()
  local a, b = m.nodes[n1].pos, m.nodes[n2].pos
  local ab = b - a
  local t = math.max(0, math.min(1, ((x - a.x) * ab.x + (y - a.y) * ab.y) / math.max(1e-6, ab.x * ab.x + ab.y * ab.y)))
  return vec3(a.x + ab.x * t, a.y + ab.y * t, 0), vec3(ab.x, ab.y, 0):normalized(), n1, n2
end

-- ---------------------------------------------------------------- camera moves on the virtual clock
local function orbitPose(s, u)
  local k = smooth(u)
  local c = vec3(s.centre[1], s.centre[2], s._gz)
  local d = s.dist[1] + (s.dist[2] - s.dist[1]) * k
  local az = math.rad(s.az[1] + (s.az[2] - s.az[1]) * k)
  local el = math.rad(s.el[1] + (s.el[2] - s.el[1]) * k)
  local cam = c + vec3(d * math.cos(el) * math.sin(az), d * math.cos(el) * math.cos(az), d * math.sin(el))
  local g = ground(cam.x, cam.y) + 1.2                   -- never under the ground (low arcs in the villages)
  if cam.z < g then cam.z = g end
  return cam, c + vec3(0, 0, s.look_dz or 0)
end

local function pathPose(s, u)
  local k = smooth(u)
  return catmull(s._pos, k), catmull(s._look, k)
end

local function walkPose(s, u)
  local p = s._a + (s._b - s._a) * smooth(u)
  local g = ground(p.x, p.y)
  s._gs = s._gs and (s._gs + (g - s._gs) * 0.08) or g      -- eye height over a smoothed ground (kerbs)
  local cam = vec3(p.x, p.y, s._gs + s.eye)
  local fwd = (s._b - s._a):normalized()
  return cam, cam + fwd * 40 + vec3(0, 0, -1.2)
end

local function stillPose(s, u)
  local yaw = math.rad(s.yaw_deg)
  local pit = math.rad(s.pitch or 0)
  local cam = vec3(s.cam[1], s.cam[2], ground(s.cam[1], s.cam[2]) + s.eye)
  return cam, cam + vec3(math.sin(yaw) * math.cos(pit), math.cos(yaw) * math.cos(pit), math.sin(pit)) * 50
end

local prepareRoad                                    -- below, with the road walk
local function prepare(s)
  if s.kind == 'orbit' then
    s._gz = ground(s.centre[1], s.centre[2])
  elseif s.kind == 'path' then
    s._pos, s._look = {}, {}
    for _, k in ipairs(s.keys) do
      local p, l = k.pos, k.look
      table.insert(s._pos, vec3(p[1], p[2], (k.agl ~= false) and ground(p[1], p[2]) + p[3] or p[3]))
      table.insert(s._look, vec3(l[1], l[2], (k.agl ~= false) and ground(l[1], l[2]) + l[3] or l[3]))
    end
  elseif s.kind == 'walk' then
    local pa = snapRoad(s.start[1], s.start[2])
    local pb = snapRoad(s['end'][1], s['end'][2])
    if pa and pb and (pb - pa):length() > 1 then
      local dir = (pb - pa):normalized()
      local side = vec3(dir.y, -dir.x, 0)                   -- right of the walking direction (the pavement)
      s._a, s._b = pa + side * (s.side or 0), pb + side * (s.side or 0)
    else
      s._a, s._b = vec3(s.start[1], s.start[2], 0), vec3(s['end'][1], s['end'][2], 0)
    end
    s._gs = nil
  elseif s.kind == 'road' then
    prepareRoad(s)
  end
end

-- road: eye height along the game's AI road from a point to a point (map.getPath), offset to the side,
-- looking ahead along the road; the polyline is resampled by length and its direction smoothed
local function polyAt(R, s)
  local n = #R.pts
  if s <= 0 then return R.pts[1] end
  if s >= R.cum[n] then return R.pts[n] end
  local lo, hi = 1, n
  while hi - lo > 1 do local m = math.floor((lo + hi) / 2); if R.cum[m] <= s then lo = m else hi = m end end
  local t = (s - R.cum[lo]) / math.max(1e-6, R.cum[hi] - R.cum[lo])
  return R.pts[lo] + (R.pts[hi] - R.pts[lo]) * t
end

local function roadPose(s, u)
  local R = s._road
  local d = R.s0 + (R.s1 - R.s0) * smooth(u)
  local a, b = polyAt(R, d - 6), polyAt(R, d + 6)
  local dir = vec3(b.x - a.x, b.y - a.y, 0):normalized()
  local p = polyAt(R, d) + vec3(dir.y, -dir.x, 0) * (s.side or 0)
  local g = ground(p.x, p.y)
  s._gs = s._gs and (s._gs + (g - s._gs) * 0.08) or g
  local cam = vec3(p.x, p.y, s._gs + (s.eye or 1.7))
  local ahead = polyAt(R, d + (s.ahead or 25)) + vec3(dir.y, -dir.x, 0) * (s.side or 0) * 0.5
  local tgt = vec3(ahead.x, ahead.y, ground(ahead.x, ahead.y) + (s.eye or 1.7) - 0.3 + (s.look_dz or 0))
  return cam, tgt
end

prepareRoad = function(s)
  local _, _, a1, a2 = snapRoad(s.start[1], s.start[2])
  local _, _, b1, b2 = snapRoad(s['end'][1], s['end'][2])
  local path = (a1 and b1) and map.getPath(a1, b1) or {}
  local m = map.getMap()
  local pts, cum = {}, {0}
  for _, n in ipairs(path) do table.insert(pts, vec3(m.nodes[n].pos.x, m.nodes[n].pos.y, 0)) end
  if #pts < 2 then pts = {vec3(s.start[1], s.start[2], 0), vec3(s['end'][1], s['end'][2], 0)} end
  for i = 2, #pts do cum[i] = cum[i - 1] + (pts[i] - pts[i - 1]):length() end
  -- a light smoothing of the node polyline (three passes of a 1-2-1 kernel), then the arc length again
  for _ = 1, 3 do
    local q = {pts[1]}
    for i = 2, #pts - 1 do q[i] = (pts[i - 1] + pts[i] * 2 + pts[i + 1]) * 0.25 end
    q[#pts] = pts[#pts]; pts = q
  end
  for i = 2, #pts do cum[i] = cum[i - 1] + (pts[i] - pts[i - 1]):length() end
  local len = cum[#pts]
  local s0 = s.skip or 0
  local s1 = math.min(len - (s.ahead or 25), s0 + (s.dist or 15))
  s._road = {pts = pts, cum = cum, s0 = s0, s1 = math.max(s0 + 1, s1)}
  s._gs = nil
  log('I', 'magliaso_trailer', string.format('road %s: %d nodes, %.0f m, walk %.0f..%.0f', s.name, #pts, len, s0, s1))
end

local POSE = {orbit = orbitPose, path = pathPose, walk = walkPose, still = stillPose, road = roadPose}

-- ---------------------------------------------------------------- cars
local function spawnCar(s)
  local a = s.route[1]
  local p, d, n1, n2 = snapRoad(a[1], a[2])
  if not p then return nil end
  local b = s.route[2]                                      -- the first waypoint gives the direction
  if d:dot(vec3(b[1] - a[1], b[2] - a[2], 0)) < 0 then d = -d end
  p = p + vec3(d.y, -d.x, 0) * (s.lane or 1.8)              -- in the right-hand lane
  p.z = ground(p.x, p.y) + 0.3
  local veh = core_vehicles.spawnNewVehicle(s.car or 'etk800', {pos = p, rot = quatFromDir(d, vec3(0, 0, 1)),
    config = s.config, autoEnterVehicle = false})
  if not veh then return nil end
  -- the game's car front is its -Y: turn it round if it came out backwards
  local fwd = veh:getDirectionVector()
  if fwd and vec3(fwd.x, fwd.y, 0):dot(d) < 0 then
    local q = quatFromDir(-d, vec3(0, 0, 1))
    veh:setPositionRotation(p.x, p.y, p.z, q.x, q.y, q.z, q.w)
  end
  -- every later point of the route a waypoint (its closest road node), so the AI keeps to the chosen road
  local wps, last = {}, nil
  for k = 2, #s.route do
    local _, _, m1, m2 = snapRoad(s.route[k][1], s.route[k][2])
    local m = m2 or m1
    if m and m ~= last then table.insert(wps, string.format('%q', m)); last = m end
  end
  veh:queueLuaCommand(string.format(
    'ai.driveUsingPath({wpTargetList = {%s}, routeSpeed = %f, routeSpeedMode = "%s", driveInLane = "on", aggression = %f, avoidCars = "on"})',
    table.concat(wps, ', '), s.speed or 13, s.speed_mode or 'limit', s.aggression or 0.3))
  return veh
end

local function carFrame(veh, st, dt)
  local p = veh:getPosition()
  local f = veh:getDirectionVector()
  f = vec3(f.x, f.y, 0):normalized()
  local a = 1 - math.exp(-dt / 0.5)                         -- heading smoothed over half a second
  st.f = st.f and (st.f + (f - st.f) * a):normalized() or f
  st.p = st.p and (st.p + (vec3(p.x, p.y, p.z) - st.p) * (1 - math.exp(-dt / 0.08))) or vec3(p.x, p.y, p.z)
  return st.p, st.f, vec3(st.f.y, -st.f.x, 0)
end

local RIG = {
  chase_low = function(p, f, r) return p - f * 6.5 + vec3(0, 0, 1.0), p + f * 3 + vec3(0, 0, 0.6) end,
  front34 = function(p, f, r) return p + f * 7 + r * 3 + vec3(0, 0, 0.8), p + vec3(0, 0, 0.7) end,
  side = function(p, f, r) return p + r * 6 + f * 0.5 + vec3(0, 0, 1.1), p + f * 1.0 + vec3(0, 0, 0.7) end,
  heli = function(p, f, r) return p - f * 28 + r * 12 + vec3(0, 0, 18), p + f * 8 end,
}

-- ---------------------------------------------------------------- saving frames
local function saveFrame(job, dir, i, t, csv)
  local name = string.format('%s/%05d', dir, i)
  createScreenshot2({filename = name, writeJPG = false, superSampling = 1})
  local waited = 0
  repeat job.sleep(0.02); waited = waited + 0.02 until FS:fileExists(name .. '.png') or waited > 4
  table.insert(csv, string.format('%05d.png,%.5f', i, t))
end

local function renderShot(job, s, cfg)
  local dir = ROOT .. '/' .. s.name
  if not FS:directoryExists(dir) then FS:directoryCreate(dir, true) end
  setTod(s.tod)
  local fps = cfg.fps or 60
  local total = s.secs + 2 * (s.handle or 0)
  local csv = {'file,t'}
  log('I', 'magliaso_trailer', 'shot ' .. s.name .. ' ' .. s.kind)

  if POSE[s.kind] then
    pausePhysics(true)
    prepare(s)
    local function at(u) local c, l = POSE[s.kind](s, u); look(c, l, s.fov or 60) end
    -- streaming, LOD and far trees settle: first a slow pass over the whole move, then back to its start
    for k = 0, (cfg.warm_steps or 4) do at(k / (cfg.warm_steps or 4)); job.sleep(cfg.warm or 2.5) end
    at(0); job.sleep(cfg.settle or 8)
    if cfg.scout then
      for k, u in ipairs({0, 0.5, 1}) do at(u); job.sleep(3.0); saveFrame(job, dir, k, u * total, csv) end
    else
      local n = math.floor(total * fps + 0.5)
      for i = 0, n do
        at(i / n); waitFrames(job, 2)
        saveFrame(job, dir, i, i / fps, csv)
      end
    end
  else                                                      -- follow / gameplay: an AI car, physics stepped per frame
    pausePhysics(false)
    if s.traffic and gameplay_traffic then pcall(function() gameplay_traffic.setupTraffic(s.traffic) end) end
    local veh = spawnCar(s)
    if not veh then log('E', 'magliaso_trailer', 'no car for ' .. s.name); return end
    be:enterVehicle(0, veh)
    local st = {}
    local static                                            -- tele: a camera on the roadside, ahead of the car
    if s.kind == 'gameplay' then core_camera.setByName(0, 'orbit') else commands.setFreeCamera() end
    job.sleep(s.preroll or cfg.preroll or 8)                -- the car gets going (and its spawn fade is over)
    simT = 0
    local p0, f0, r0 = carFrame(veh, st, 1)
    if s.rig == 'tele' then
      local ahead = p0 + f0 * ((s.speed or 13) * total * 0.55)
      static = ahead + vec3(f0.y, -f0.x, 0) * 9
      static.z = ground(static.x, static.y) + 1.6
    end
    -- physics running all the time in deep slow motion (2 % by default: the AI sees ordinary small time
    -- steps); a frame is saved whenever the simulation time passes the next 1/fps mark, with its exact
    -- simulation time, so a save that takes half a second moves the car by a few millimetres only
    local scale = cfg.timescale or 0.02
    local n = math.floor(total * fps + 0.5)
    local keep = {}
    if cfg.scout then keep = {[0] = true, [math.floor(n / 2)] = true, [n] = true} end
    local t0real = os.time()
    local function setScale(k)
      if not pcall(function() simTimeAuthority.setInstant(k) end) then be:setSimulationTimeScale(k) end
      be:setSimulationTimeScale(k)
    end
    setScale(scale)
    waitFrames(job, 2)
    simT = 0
    local pPrev, i, lastT = nil, 0, 0
    while i <= n do
      if os.time() - t0real > (cfg.shot_timeout or 1500) then log('E', 'magliaso_trailer', 'timeout ' .. s.name); break end
      waitFrames(job, 1)
      local p, f, r = carFrame(veh, st, simT - lastT); lastT = simT
      if s.kind == 'follow' then
        local cam, tgt
        if static then cam, tgt = static, p + vec3(0, 0, 0.7) else cam, tgt = RIG[s.rig](p, f, r) end
        local g = ground(cam.x, cam.y) + 0.4
        if cam.z < g then cam.z = g end
        look(cam, tgt, s.fov or 55)
      end
      if simT >= i / fps then
        if i == 1 or i == math.floor(n / 2) or i == n then
          local v = veh:getVelocity()
          log('I', 'magliaso_trailer', string.format('%s frame %d t %.4f moved %.3f m speed %.2f m/s', s.name, i, simT,
            pPrev and (p - pPrev):length() or -1, v and vec3(v.x, v.y, v.z):length() or -1))
        end
        pPrev = p
        if not cfg.scout or keep[i] then saveFrame(job, dir, i, simT, csv) end
        i = i + 1
      end
    end
    setScale(1.0)
    be:exitVehicle(0)
    veh:delete()
    if s.traffic and gameplay_traffic then pcall(function() gameplay_traffic.deleteVehicles() end) end
    commands.setFreeCamera()
  end
  writeFile(dir .. '/frames.csv', table.concat(csv, '\n') .. '\n')
end

local function run()
  if started then return end
  started = true
  local cfg = jsonReadFile('/magliaso_trailer_shots.json') or {}
  core_jobsystem.create(function(job)
    local bgOld = settings.getValue('fpsLimitBackgroundEnabled')
    pcall(function() settings.setValue('fpsLimitBackgroundEnabled', false) end)   -- full speed behind the black window
    if not FS:directoryExists(ROOT) then FS:directoryCreate(ROOT, true) end
    writeFile(ROOT .. '/_ready.txt', 'ready')
    job.sleep(3.0)
    local veh = be:getPlayerVehicle(0)
    if veh then pcall(function() veh:delete() end) end           -- the default car never in a shot
    pcall(function() extensions.unload('gameplay_markerInteraction') end)
    if extensions.ui_visibility then extensions.ui_visibility.setCef(false) end   -- no HUD
    if cfg.video then                                       -- borderless at the frame size (not saved to the settings)
      pcall(function() GFXDevice.setVideoMode({width = cfg.video[1], height = cfg.video[2], refreshRate = 60, displayMode = 'Borderless'}) end)
      job.sleep(3.0)
    end
    commands.setFreeCamera()
    pcall(function() map.assureLoad() end)
    for _, s in ipairs(cfg.shots or {}) do
      local ok, err = pcall(renderShot, job, s, cfg)
      if not ok then log('E', 'magliaso_trailer', s.name .. ': ' .. tostring(err)) end
      writeFile(ROOT .. '/_progress.txt', s.name)
    end
    pcall(function() settings.setValue('fpsLimitBackgroundEnabled', bgOld) end)
    writeFile(ROOT .. '/_done.txt', 'done')
    log('I', 'magliaso_trailer', 'DONE')
    job.sleep(2.0)
    shutdown(0)
  end)
end

M.onUpdate = function(dtReal, dtSim) simT = simT + (dtSim or 0); lastReal = dtReal or lastReal; frameNo = frameNo + 1 end
M.onClientPostStartMission = function() run() end
M.onWorldReadyState = function(state) if state == 2 then run() end end
return M
