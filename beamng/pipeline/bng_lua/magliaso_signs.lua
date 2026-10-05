-- Road-sign screenshots of the magliaso_pura level (v2.7): the README tour, with the fps of every view in the log.
-- Loaded with:  BeamNG.drive.x64.exe -level magliaso_pura -onLevelLoad_ext magliaso_signs
-- Reads <user>/magliaso_signs_views.json (written by the caller): per view the camera and
-- target x, y, their heights above the ground (cam_dz, target_dz; from_target = the camera height is
-- taken above the target's ground), fov and wait. The ground is the game's own surface (terrain, roads,
-- bridges); target_z / cam_z, when given, are absolute heights. Places the free camera at each view without HUD and without the player's car, saves
-- <user>/screenshots/magliaso_signs/<name>.png and quits when done.
local M = {}
local started = false
local frames, ftime = 0, 0
local DIR = 'screenshots/magliaso_signs'

local function ground(x, y)
  local ok, h = pcall(function() return be:getSurfaceHeightBelow(vec3(x, y, 3000)) end)
  if ok and h and h > -1000 then return h end
  return core_terrain.getTerrainHeight(vec3(x, y, 0)) or 0
end

local function run()
  if started then return end
  started = true
  local views = jsonReadFile('/magliaso_signs_views.json') or {}
  log('I', 'magliaso_signs', 'views: ' .. tostring(#views))
  core_jobsystem.create(function(job)
    job.sleep(3.0)
    local veh = be:getPlayerVehicle(0)
    if veh then veh:setPositionRotation(0, 0, -500, 0, 0, 0, 1) end   -- out of sight
    commands.setFreeCamera()
    if extensions.ui_visibility then extensions.ui_visibility.setCef(false) end   -- no HUD in the shots
    if not FS:directoryExists(DIR) then FS:directoryCreate(DIR, true) end
    job.sleep(1.0)
    pcall(function() map.assureLoad() end)
    for i, v in ipairs(views) do
      if v.snap_road then   -- onto the closest road, looking along it on the side of the original target
        local ok, err = pcall(function()
          local n1, n2 = map.findClosestRoad(vec3(v.cam[1], v.cam[2], ground(v.cam[1], v.cam[2])))
          local m = map.getMap()
          local a, b = m.nodes[n1].pos, m.nodes[n2].pos
          local ab = b - a
          local t = math.max(0, math.min(1, ((v.cam[1] - a.x) * ab.x + (v.cam[2] - a.y) * ab.y) / (ab.x * ab.x + ab.y * ab.y)))
          local cx, cy = a.x + ab.x * t, a.y + ab.y * t
          local d = vec3(ab.x, ab.y, 0):normalized()
          if d.x * (v.target[1] - v.cam[1]) + d.y * (v.target[2] - v.cam[2]) < 0 then d = -d end
          v.cam = {cx, cy}
          v.target = {cx + d.x * 60, cy + d.y * 60}
        end)
        if not ok then log('E', 'magliaso_signs', 'snap_road failed: ' .. tostring(err)) end
      end
      local zt = ground(v.target[1], v.target[2]) + (v.target_dz or 0)
      local zc = (v.from_target and ground(v.target[1], v.target[2]) or ground(v.cam[1], v.cam[2])) + v.cam_dz
      if v.target_z then zt = v.target_z end   -- absolute heights: the probe from above also hits roofs and props
      if v.cam_z then zc = v.cam_z end
      local dx, dy, dz = v.target[1] - v.cam[1], v.target[2] - v.cam[2], zt - zc
      local yaw = math.deg(math.atan2(dx, dy)) % 360                    -- compass, 0 = north
      local pitch = v.pitch or math.deg(math.atan2(dz, math.sqrt(dx * dx + dy * dy)))   -- + = up
      core_camera.setPosition(0, vec3(v.cam[1], v.cam[2], zc))
      core_camera.setFreeCameraYawPitchRollDeg(yaw, -pitch, 0)
      if v.fov then core_camera.setFOV(0, v.fov) end
      log('I', 'magliaso_signs', string.format('view %s cam %.1f %.1f %.1f yaw %.1f pitch %.1f',
        v.name, v.cam[1], v.cam[2], zc, yaw, pitch))
      job.sleep((v.wait or 10.0) - 3.0)  -- let streaming, LOD and the forest settle
      frames, ftime = 0, 0              -- then 3 s of frames for the fps
      job.sleep(3.0)
      log('I', 'magliaso_signs', string.format('fps %s %.1f', v.name, frames / math.max(ftime, 1e-3)))
      createScreenshot2({filename = DIR .. '/' .. v.name, writeJPG = false, superSampling = 1})
      job.sleep(1.5)
      log('I', 'magliaso_signs', 'shot ' .. v.name)
    end
    job.sleep(2.0)
    writeFile(DIR .. '/_done.txt', 'done')
    log('I', 'magliaso_signs', 'DONE')
    shutdown(0)
  end)
end

M.onUpdate = function(dtReal) frames = frames + 1; ftime = ftime + dtReal end
M.onClientPostStartMission = function() run() end
M.onWorldReadyState = function(state) if state == 2 then run() end end
return M
