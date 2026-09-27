-- Validation camera tour for the magliaso_pura level.
-- Loaded with:  BeamNG.drive.x64.exe -level magliaso_pura -onLevelLoad_ext magliaso_validate
-- Reads /levels/magliaso_pura/validation_views.json (list of {name, pos=[x,y,z], yaw, pitch, fov}),
-- places the free camera at each Street View pose, saves a screenshot to
-- <user>/screenshots/magliaso/<name>.png and quits when done.
local M = {}
local started = false

local function run()
  if started then return end
  started = true
  local views = jsonReadFile('/levels/magliaso_pura/validation_views.json') or {}
  log('I', 'magliaso_validate', 'views: ' .. tostring(#views))
  core_jobsystem.create(function(job)
    job.sleep(3.0)
    local veh = be:getPlayerVehicle(0)
    if veh then
      local d = veh:getDirectionVector()
      local p = veh:getPosition()
      log('I', 'magliaso_validate', string.format('SPAWNDIR pos %.2f %.2f dir %.4f %.4f %.4f', p.x, p.y, d.x, d.y, d.z))
      -- top-down shot of the spawned car (north up) to check its alignment with the road
      commands.setFreeCamera()
      if extensions.ui_visibility then extensions.ui_visibility.setCef(false) end
      if not FS:directoryExists('screenshots/magliaso') then FS:directoryCreate('screenshots/magliaso', true) end
      core_camera.setPosition(0, vec3(p.x, p.y, p.z + 18))
      core_camera.setFreeCameraYawPitchRollDeg(0, 89, 0)
      core_camera.setFOV(0, 70)
      job.sleep(2.5)
      createScreenshot2({filename = 'screenshots/magliaso/_spawn_top', writeJPG = false, superSampling = 1})
      job.sleep(0.8)
      veh:setPositionRotation(0, 0, -500, 0, 0, 0, 1)   -- out of sight
    end
    commands.setFreeCamera()
    if extensions.ui_visibility then extensions.ui_visibility.setCef(false) end   -- no HUD in the shots
    job.sleep(1.0)
    -- AI road network check: node count and a route along the Strada Cantonale
    local ok, err = pcall(function()
      map.assureLoad()
      local m = map.getMap()
      local n, e = 0, 0
      for id, node in pairs(m.nodes or {}) do
        n = n + 1
        for _ in pairs(node.links or {}) do e = e + 1 end
      end
      log('I', 'magliaso_validate', 'NAVGRAPH nodes ' .. n .. ' links ' .. e)
      local ends = jsonReadFile('/levels/magliaso_pura/validation_route.json')
      if ends then
        local a = vec3(ends[1][1], ends[1][2], ends[1][3])
        local b = vec3(ends[2][1], ends[2][2], ends[2][3])
        local path = map.getPointToPointPath(a, b)
        local len = 0
        if path and #path > 1 then
          local pos = map.getPathPositions and nil
          for i = 2, #path do
            local p1, p2 = m.nodes[path[i - 1]].pos, m.nodes[path[i]].pos
            len = len + (p1 - p2):length()
          end
        end
        log('I', 'magliaso_validate', 'NAVGRAPH route nodes ' .. tostring(path and #path or 0) .. ' length ' .. string.format('%.0f', len))
      end
    end)
    if not ok then log('E', 'magliaso_validate', 'navgraph check failed: ' .. tostring(err)) end
    if not FS:directoryExists('screenshots/magliaso') then FS:directoryCreate('screenshots/magliaso', true) end
    for i, v in ipairs(views) do
      core_camera.setPosition(0, vec3(v.pos[1], v.pos[2], v.pos[3]))
      core_camera.setFreeCameraYawPitchRollDeg(v.yaw, -(v.pitch or 0), 0)
      if v.fov then core_camera.setFOV(0, v.fov) end
      job.sleep(v.wait or 2.5)          -- let streaming / LOD settle
      createScreenshot2({filename = 'screenshots/magliaso/' .. v.name, writeJPG = v.jpg and true or false, superSampling = 1})
      job.sleep(0.8)
      log('I', 'magliaso_validate', 'shot ' .. v.name)
    end
    job.sleep(2.0)
    writeFile('screenshots/magliaso/_done.txt', 'done')
    log('I', 'magliaso_validate', 'DONE')
    shutdown(0)
  end)
end

M.onClientPostStartMission = function() run() end
M.onWorldReadyState = function(state) if state == 2 then run() end end
return M
