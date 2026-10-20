-- Traffic and AI test of the magliaso_pura level (v3.0.40): what the game made of the AI roads, and how its traffic drives.
-- Copy to <user>/lua/ge/extensions/magliaso_traffic.lua and start the game with
--   BeamNG.drive.x64 -level magliaso_pura -onLevelLoad_ext magliaso_traffic
-- Options (optional): <user>/magliaso_traffic/options.json
--   {"traffic": 12, "parked": 30, "duration": 900, "every": 2, "quit": false}
-- Writes to <user>/magliaso_traffic/:
--   navgraph.json   every node of the game's AI graph (position, radius) and every link with all its fields
--                   (drivability, oneWay, speed limit, lanes ... as this version of the game names them)
--   signals.json    the signal points the game matched to the graph (if the module answers)
--   parking.json    the parking spots the game loaded and the parked cars it placed
--   traffic.json    every `every` s the position, speed and road of each traffic car (stuck cars show here)
--   done.txt        when the test is over
-- Nothing else is changed; remove the file from lua/ge/extensions after the test (a left-over extension runs on
-- every level).
local M = {}
local OUT = 'magliaso_traffic/'
local started = false

local function plain(t, depth)
  -- a copy of a table with only numbers, strings, booleans and vec3 (as {x, y, z}), for jsonWriteFile
  depth = depth or 0
  if depth > 3 then return nil end
  local out = {}
  for k, v in pairs(t) do
    local tv = type(v)
    if tv == 'number' or tv == 'string' or tv == 'boolean' then
      out[tostring(k)] = v
    elseif tv == 'table' then
      out[tostring(k)] = plain(v, depth + 1)
    elseif tv == 'userdata' or tv == 'cdata' then
      local ok, x = pcall(function() return {v.x, v.y, v.z} end)
      if ok and x[1] then out[tostring(k)] = x end
    end
  end
  return out
end

local function dumpGraph()
  map.assureLoad()
  local m = map.getMap()
  local nodes, n, e = {}, 0, 0
  for id, node in pairs(m.nodes or {}) do
    n = n + 1
    local links = {}
    for other, link in pairs(node.links or {}) do
      e = e + 1
      links[tostring(other)] = plain(link)
    end
    local p = node.pos
    nodes[tostring(id)] = {pos = {p.x, p.y, p.z}, radius = node.radius, links = links}
  end
  jsonWriteFile(OUT .. 'navgraph.json', {nodes = nodes, count = n, links = e}, false)
  log('I', 'magliaso_traffic', string.format('NAVGRAPH nodes %d links %d', n, e))
end

local function dumpSignals()
  local mod = extensions.core_trafficSignals
  if not mod then log('W', 'magliaso_traffic', 'no core_trafficSignals') return end
  local data = {}
  for _, fn in ipairs({'getValues', 'getSignals', 'getSignalsDict', 'getMapNodeSignals', 'getData'}) do
    if type(mod[fn]) == 'function' then
      local ok, r = pcall(mod[fn])
      if ok and type(r) == 'table' then data[fn] = plain(r) end
    end
  end
  jsonWriteFile(OUT .. 'signals.json', data, false)
end

local function dumpParking()
  local data = {}
  local ok, sites = pcall(function() return gameplay_city and gameplay_city.getSites() end)
  if ok and sites and sites.parkingSpots then
    data.spots = #(sites.parkingSpots.sorted or {})
  end
  local mod = extensions.gameplay_parking
  if mod then
    for _, fn in ipairs({'getParkedCarsList', 'getParkingSpots', 'getState', 'getVars'}) do
      if type(mod[fn]) == 'function' then
        local ok2, r = pcall(mod[fn])
        if ok2 and type(r) == 'table' then data[fn] = plain(r) end
      end
    end
  end
  jsonWriteFile(OUT .. 'parking.json', data, false)
  log('I', 'magliaso_traffic', 'PARKING ' .. tostring(data.spots))
end

local function run()
  if started then return end
  started = true
  local opt = jsonReadFile(OUT .. 'options.json') or {}
  local nTraffic, nParked = opt.traffic or 12, opt.parked or 30
  local duration, every = opt.duration or 900, opt.every or 2
  if not FS:directoryExists(OUT) then FS:directoryCreate(OUT, true) end
  core_jobsystem.create(function(job)
    job.sleep(5.0)
    local ok, err = pcall(dumpGraph)
    if not ok then log('E', 'magliaso_traffic', 'navgraph: ' .. tostring(err)) end
    ok, err = pcall(dumpSignals)
    if not ok then log('E', 'magliaso_traffic', 'signals: ' .. tostring(err)) end
    if nParked > 0 and gameplay_parking then
      ok, err = pcall(gameplay_parking.setupVehicles, nParked)
      if not ok then log('E', 'magliaso_traffic', 'parking: ' .. tostring(err)) end
    end
    if nTraffic > 0 and gameplay_traffic then
      ok, err = pcall(gameplay_traffic.setupTraffic, nTraffic)
      if not ok then log('E', 'magliaso_traffic', 'traffic: ' .. tostring(err)) end
    end
    job.sleep(20.0)
    pcall(dumpParking)
    local samples, t = {}, 0
    while t < duration do
      local rows = {}
      local tr = gameplay_traffic and gameplay_traffic.getTrafficData and gameplay_traffic.getTrafficData() or {}
      for id, v in pairs(tr) do
        local obj = be:getObjectByID(id)
        if obj then
          local p, vel = obj:getPosition(), obj:getVelocity()
          local road = map.findClosestRoad and {map.findClosestRoad(p)} or {}
          rows[#rows + 1] = {id = id, t = t, x = p.x, y = p.y, z = p.z, v = vel:length(),
                             a = road[1], b = road[2], d = road[3], state = v.state, model = obj.jbeam}
        end
      end
      samples[#samples + 1] = rows
      if #samples % 30 == 0 then jsonWriteFile(OUT .. 'traffic.json', samples, false) end
      job.sleep(every)
      t = t + every
    end
    jsonWriteFile(OUT .. 'traffic.json', samples, false)
    writeFile(OUT .. 'done.txt', 'done')
    log('I', 'magliaso_traffic', 'DONE')
    if opt.quit then shutdown(0) end
  end)
end

M.onClientPostStartMission = function() run() end
M.onWorldReadyState = function(state) if state == 2 then run() end end
return M
