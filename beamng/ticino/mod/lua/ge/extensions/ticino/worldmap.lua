-- Ticino map (GE extension 'ticino_worldmap'): the M key and the pause menu's Map open a 2D map of the whole of Ticino
-- instead of the stock big map, in the level ticino only.
--
-- The stock big map (freeroam/bigMapMode.lua) is a 3D camera over the loaded level: in Ticino that is the ~3 km terrain
-- window round the car, nothing else (michi 2026-10-31: "se schiacci la m ... compare la mappa del ticino completa").
-- The idea and the way in are BeamNG.Earth's (c) 2026 TecnaGamer, MIT licence (github.com/TecnaGamer/BeamNG.Earth:
-- settings.lua redirectBigMap / toggleMap, ui/ui-vue/mods/beamngEarth/index.js and EarthMap.vue): toggleBigMap and
-- enterBigMap of freeroam_bigMapMode point at our own UI route while the level ticino runs, and back when it ends.
-- The page (ui/ui-vue/mods/ticino/TicinoMap.vue) draws the image tiles of levels/ticino/map/ (worldmap.py: the
-- level's own ground colours and AI roads, every zone), the car, and the spawn points by their real names; a click
-- on a place takes the car there (as the stock map's spawn points do: spawn.safeTeleport, the streamer's jump
-- makes the ground there).
--
-- Console:  ticino_worldmap.toggle()   ticino_worldmap.redirect(false)  (the stock big map again)

local M = {}

M.LEVEL = 'ticino'
M.ROUTE = 'ticinoMap'
M.INFO_FILE = '/levels/ticino/map/map.json'
M.PAUSE = true              -- the game stands still while the map is open (as the stock big map)
M.TOGGLE_GAP_S = 0.3        -- a key press seen by both the page and the action map counts once
M.REPLACE = true            -- false: leave the stock big map alone

local open = false
local orig = nil            -- the stock functions while ours are in
local lastToggle = -1
local info = nil
local paused = false
local inLevel = false

local function now() return os.clock() end

local function levelIs()
  local f = rawget(_G, 'getCurrentLevelIdentifier')
  return f and f() == M.LEVEL or false
end

local function navigate(state)
  local r = rawget(_G, 'ui_router')
  if r and r.navigate and pcall(r.navigate, state) then return true end
  local gh = rawget(_G, 'guihooks')
  if gh then gh.trigger('ChangeState', { state = state }) return true end
  return false
end

local function setPause(on)
  if not M.PAUSE or on == paused then return end
  local sta = rawget(_G, 'simTimeAuthority')
  if sta and sta.pushPauseRequest then
    if on then sta.pushPauseRequest('ticinoMap') else sta.popPauseRequest('ticinoMap') end
    paused = on
  end
end

function M.close()
  if not open then return end
  open = false
  setPause(false)
  navigate('play')
end

function M.openMap()
  if open then return end
  open = true
  setPause(true)
  local veh = rawget(_G, 'getPlayerVehicle') and getPlayerVehicle(0)
  if veh then pcall(veh.queueLuaCommand, veh, "input.event('throttle', 0, 2) input.event('brake', 0, 2)") end
  navigate(M.ROUTE)
end

function M.toggle()
  local t = now()
  if t - lastToggle < M.TOGGLE_GAP_S then return end
  lastToggle = t
  if open then M.close() else M.openMap() end
end

-- the stock big map's ways in -> ours (career keeps its own)
function M.redirect(want)
  local bm = rawget(_G, 'freeroam_bigMapMode')
  local career = rawget(_G, 'career_career')
  if career and career.isActive and career.isActive() then want = false end
  if want and M.REPLACE and bm and not orig then
    orig = { bm = bm, enter = bm.enterBigMap, toggle = bm.toggleBigMap }
    bm.toggleBigMap = function() M.toggle() end
    bm.enterBigMap = function() if not open then M.toggle() end end
    log('I', 'ticino', 'M opens the Ticino map')
  elseif not want and orig then
    orig.bm.enterBigMap, orig.bm.toggleBigMap = orig.enter, orig.toggle
    orig = nil
  end
  return orig ~= nil
end

-- ---------------------------------------------------------------- the page's calls
function M.uiInfo()
  if not info then
    local text = readFile(M.INFO_FILE)
    local ok, t = pcall(jsonDecode, text or '')
    info = ok and type(t) == 'table' and t or nil
    if not info then return { missing = true } end
  end
  return info
end

function M.uiState()
  local out = { open = open }
  local veh = rawget(_G, 'getPlayerVehicle') and getPlayerVehicle(0)
  if veh then
    local p = veh:getPosition()
    local d = veh:getDirectionVector()
    out.car = { x = p.x, y = p.y, h = math.deg(math.atan2(d.x, d.y)) % 360 }
  end
  return out
end

-- the page went away by itself (Esc, the back button): the game goes on
function M.uiClosed()
  if open then
    open = false
    setPause(false)
  end
end

function M.uiOpened()
  if not open then
    open = true
    setPause(true)
  end
end

-- the car to a spawn point (its name in the scene), as the stock map's spawn points
function M.uiGo(objectName)
  local sp = scenetree.findObject(objectName)
  local veh = rawget(_G, 'getPlayerVehicle') and getPlayerVehicle(0)
  if not sp or not veh then return { ok = false, error = 'no such place or no car' } end
  local pos, rot = sp:getPosition(), quat(0, 0, 1, 0) * sp:getRotation()
  M.close()
  spawn.safeTeleport(veh, pos, rot)
  if veh.resetBrokenFlexMesh then veh:resetBrokenFlexMesh() end
  if core_camera and core_camera.resetCamera then core_camera.resetCamera(0) end
  log('I', 'ticino', 'map: to ' .. tostring(objectName))
  return { ok = true }
end

-- ---------------------------------------------------------------- hooks
local checkAt = 0
function M.onUpdate()
  if not inLevel then return end
  local t = now()
  if t < checkAt then return end
  checkAt = t + 2
  if not orig then M.redirect(true) end     -- freeroam_bigMapMode may load after the level
end

function M.onClientPostStartMission(levelPath)
  inLevel = (type(levelPath) == 'string' and levelPath:find('/levels/' .. M.LEVEL .. '/', 1, true) ~= nil) or levelIs()
  info = nil
  open, lastToggle = false, -1
  M.redirect(inLevel)
end

function M.onClientEndMission()
  inLevel = false
  if open then M.close() end
  M.redirect(false)
end

function M.onExtensionUnloaded()
  setPause(false)
  M.redirect(false)
end

return M
