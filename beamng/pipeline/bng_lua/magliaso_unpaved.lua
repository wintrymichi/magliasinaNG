-- Dirt and gravel tracks flush with the ground (v2.7, network_mesh.unpaved_step): the in-game check.
-- Loaded with:  BeamNG.drive.x64.exe -level magliaso_pura -onLevelLoad_ext magliaso_unpaved
-- Reads <user>/magliaso_unpaved_views.json (unpaved_tour.py): a list of
--   {kind = "view", name, cam = {x, y, z}, target = {x, y, z}, fov, wait, tod}  -> screenshot <name>.png
--     (tod, optional, v2.8: the time of day, 0 noon, 0.5 midnight; set before the view if the game has
--     core_environment.setTimeOfDay, else ignored; fps, optional, v2.8: the frame rate over the last 3 s
--     of the wait, in the log and in _drive.json)
--   {kind = "drive", name, pos = {x, y, z}, dir = {x, y}, throttle, time, cam, target, fov}
--     the player's car on the track heading at the edge, throttle for `time` s: the peak vertical
--     acceleration of the body (from its velocity, frame to frame) and how far it went, in the log and
--     in _drive.json; a screenshot from `cam` halfway.
-- Shots in <user>/screenshots/magliaso_unpaved/, without HUD; quits when done.
local M = {}
local started = false
local DIR = 'screenshots/magliaso_unpaved'
local probe = nil   -- {veh, prevVz, peak, samples}
local frames, ftime = 0, 0

local function shot(name)
  createScreenshot2({filename = DIR .. '/' .. name, writeJPG = false, superSampling = 1})
end

local function place(cam, target, fov)
  local dx, dy, dz = target[1] - cam[1], target[2] - cam[2], target[3] - cam[3]
  local yaw = math.deg(math.atan2(dx, dy)) % 360
  local pitch = math.deg(math.atan2(dz, math.sqrt(dx * dx + dy * dy)))
  core_camera.setPosition(0, vec3(cam[1], cam[2], cam[3]))
  core_camera.setFreeCameraYawPitchRollDeg(yaw, -pitch, 0)
  if fov then core_camera.setFOV(0, fov) end
end

local function teleport(veh, v)
  local dir = vec3(v.dir[1], v.dir[2], 0):normalized()
  local rot = quatFromDir(dir, vec3(0, 0, 1))
  veh:setPositionRotation(v.pos[1], v.pos[2], v.pos[3], rot.x, rot.y, rot.z, rot.w)
  return dir, rot
end

local function run()
  if started then return end
  started = true
  local views = jsonReadFile('/magliaso_unpaved_views.json') or {}
  log('I', 'magliaso_unpaved', 'views: ' .. tostring(#views))
  local results = {}
  core_jobsystem.create(function(job)
    job.sleep(3.0)
    local veh = be:getPlayerVehicle(0)
    if veh then veh:setPositionRotation(0, 0, -500, 0, 0, 0, 1) end
    commands.setFreeCamera()
    if extensions.ui_visibility then extensions.ui_visibility.setCef(false) end
    if not FS:directoryExists(DIR) then FS:directoryCreate(DIR, true) end
    job.sleep(1.0)
    for _, v in ipairs(views) do
      if v.kind == 'view' then
        if v.tod and core_environment and core_environment.setTimeOfDay then
          pcall(function()
            local t = core_environment.getTimeOfDay and core_environment.getTimeOfDay() or {}
            t.time = v.tod
            t.play = false
            core_environment.setTimeOfDay(t)
          end)
        end
        place(v.cam, v.target, v.fov)
        log('I', 'magliaso_unpaved', 'view ' .. v.name)
        if v.fps then
          job.sleep(math.max((v.wait or 8.0) - 3.0, 0.5))
          frames, ftime = 0, 0
          job.sleep(3.0)
          local fps = frames / math.max(ftime, 1e-3)
          log('I', 'magliaso_unpaved', string.format('fps %s %.1f', v.name, fps))
          table.insert(results, {name = v.name, fps = fps})
        else
          job.sleep(v.wait or 8.0)
        end
        shot(v.name)
        job.sleep(1.5)
      elseif v.kind == 'drive' and veh then
        local dir, rot = teleport(veh, v)
        job.sleep(0.5)
        if veh:getDirectionVector():dot(dir) < 0 then        -- the car's forward is the other way
          local r = quatFromDir(-dir, vec3(0, 0, 1))
          veh:setPositionRotation(v.pos[1], v.pos[2], v.pos[3], r.x, r.y, r.z, r.w)
        end
        veh:queueLuaCommand('input.event("throttle", 0, 1); input.event("brake", 0, 1); input.event("parkingbrake", 0, 1); input.event("steering", 0, 1)')
        place(v.cam, v.target, v.fov)
        job.sleep(3.0)                                        -- settle on the wheels
        local p0 = veh:getPosition()
        probe = {veh = veh, prevVz = nil, peak = 0, n = 0, zmin = p0.z, zmax = p0.z}
        local headingDot = veh:getDirectionVector():dot(dir)
        -- the car stands in park / neutral and the throttle alone does not move it: first gear
        veh:queueLuaCommand('if controller.mainController.shiftToGearIndex then controller.mainController.shiftToGearIndex(1) end')
        veh:queueLuaCommand(string.format('input.event("throttle", %.2f, 1)', v.throttle or 0.4))
        job.sleep((v.time or 4.0) / 2)
        shot(v.name)
        job.sleep((v.time or 4.0) / 2)
        veh:queueLuaCommand('input.event("throttle", 0, 1); input.event("brake", 1, 1)')
        local p1 = veh:getPosition()
        local d = p1 - p0
        local r = {name = v.name, peak_az = probe.peak, frames = probe.n, heading_dot = headingDot,
                   along = d.x * dir.x + d.y * dir.y, dz = d.z,
                   speed = veh:getVelocity():length(), end_pos = {p1.x, p1.y, p1.z}}
        probe = nil
        table.insert(results, r)
        log('I', 'magliaso_unpaved', string.format('drive %s peak_az %.1f m/s2 frames %d along %.1f m dz %.2f m',
          v.name, r.peak_az, r.frames, r.along, r.dz))
        job.sleep(2.0)
        veh:queueLuaCommand('input.event("brake", 0, 1)')
        veh:setPositionRotation(0, 0, -500, 0, 0, 0, 1)
        job.sleep(1.0)
      end
    end
    jsonWriteFile(DIR .. '/_drive.json', results, true)
    job.sleep(2.0)
    writeFile(DIR .. '/_done.txt', 'done')
    log('I', 'magliaso_unpaved', 'DONE')
    shutdown(0)
  end)
end

M.onUpdate = function(dtReal, dtSim)
  frames = frames + 1
  ftime = ftime + (dtReal or 0)
  if not probe or not dtSim or dtSim <= 0 then return end
  local vz = probe.veh:getVelocity().z
  if probe.prevVz then
    local az = math.abs(vz - probe.prevVz) / dtSim
    if az > probe.peak then probe.peak = az end
    probe.n = probe.n + 1
  end
  probe.prevVz = vz
end
M.onClientPostStartMission = function() run() end
M.onWorldReadyState = function(state) if state == 2 then run() end end
return M
