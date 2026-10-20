-- MagliasinaNG ambient sounds (v3.0.40): the timing of the emitters ambient_sounds.py places in the level
-- (MissionGroup/ambient_sounds):
--   ambient_day    birds:    playing from DAY_FROM to DAY_TO o'clock, stopped at night
--   ambient_night  crickets: playing at night, stopped by day
--   ambient_bells  church bells: rung on the hour from BELL_FIRST to BELL_LAST o'clock, stopped after RING_S s
--   ambient_water  rivers, streams, the lake: always (playOnAdd), not touched here
-- Only on the map magliaso_pura; every call to the game is guarded, a missing function only leaves the sounds as
-- the level starts them. The game counts the time of day from 0 (noon) to 1, 0.5 is midnight.
local M = {}

local LEVEL = 'magliaso_pura'
local DAY_FROM, DAY_TO = 5.5, 20.5
local BELL_FIRST, BELL_LAST = 7, 21
local RING_S = 30
local CHECK_S = 1.0

local active, groups = false, {}
local timer, lastHour, isDay, ringLeft = 0, nil, nil, nil

local function members(name)
  local out = {}
  local g = scenetree.findObject(name)
  if not g or not g.getCount then return out end
  for i = 0, g:getCount() - 1 do
    local o = g:getObject(i)
    if o then table.insert(out, o) end
  end
  return out
end

local function setPlaying(list, on)
  for _, o in ipairs(list) do
    pcall(function() if on then o:play() else o:stop() end end)
  end
end

local function hourNow()
  if not core_environment or not core_environment.getTimeOfDay then return nil end
  local ok, t = pcall(core_environment.getTimeOfDay)
  if not ok or type(t) ~= 'table' or type(t.time) ~= 'number' then return nil end
  return ((t.time % 1) * 24 + 12) % 24
end

local function start()
  local mission = getMissionFilename and getMissionFilename() or ''
  active = string.find(mission, '/' .. LEVEL .. '/', 1, true) ~= nil
  groups, lastHour, isDay, ringLeft, timer = {}, nil, nil, nil, 0
  if not active then return end
  groups.day = members('ambient_day')
  groups.night = members('ambient_night')
  groups.bells = members('ambient_bells')
  log('I', 'magliasoAmbient', string.format('day %d, night %d, bells %d', #groups.day, #groups.night, #groups.bells))
end

local function onUpdate(dtReal)
  if not active then return end
  timer = timer + (dtReal or 0)
  if ringLeft then
    ringLeft = ringLeft - (dtReal or 0)
    if ringLeft <= 0 then setPlaying(groups.bells, false); ringLeft = nil end
  end
  if timer < CHECK_S then return end
  timer = 0
  local h = hourNow()
  if not h then return end
  local day = h >= DAY_FROM and h < DAY_TO
  if day ~= isDay then
    setPlaying(groups.day, day)
    setPlaying(groups.night, not day)
    isDay = day
  end
  local hour = math.floor(h)
  if lastHour and hour ~= lastHour and hour >= BELL_FIRST and hour <= BELL_LAST then
    setPlaying(groups.bells, true)
    ringLeft = RING_S
  end
  lastHour = hour
end

M.onClientPostStartMission = start
M.onClientEndMission = function() active = false; groups = {} end
M.onUpdate = onUpdate
M.onExtensionLoaded = function() if getMissionFilename and getMissionFilename() ~= '' then start() end end

return M
