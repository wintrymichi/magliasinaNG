-- Outside the game: stream.lua driven along a straight line at 120 km/h with the game's API stubbed, to catch Lua
-- errors and count what it does (jumps, moves, objects made and kept, far tiles hidden).
--   luajit sim_stream.lua <out dir of blocks.py> [seconds]
local here = arg[0]:gsub('[^/]*$', '')
package.path = here .. '../mod/lua/ge/extensions/?.lua;' .. package.path
local root, seconds = arg[1], tonumber(arg[2] or '120')

-- ---- stubs of the game API (only what stream.lua, objects.lua and terwin.lua call)
local function mapPath(p) return (p:gsub('^/levels/', root .. '/levels/'):gsub('^/temp/', root .. '/temp/')) end
local realOpen = io.open
io.open = function(p, mode) return realOpen(mapPath(p), mode) end
function readFile(p) local f = io.open(p, 'rb'); if not f then return nil end; local s = f:read('*a'); f:close(); return s end
function writeFile(p, s) local f = io.open(p:sub(1, 1) == '/' and p:gsub('^/', '/temp/') or p, 'wb'); if f then f:write(s); f:close() end; return true end
-- a small JSON decoder (enough for stream.json and the tile files)
function jsonDecode(s)
  local pos = 1
  local function ws() pos = s:find('[^ \t\r\n]', pos) or #s + 1 end
  local val
  local function str()
    local e = pos + 1
    local out = {}
    while true do
      local c = s:sub(e, e)
      if c == '"' then break end
      if c == '\\' then out[#out + 1] = s:sub(e + 1, e + 1); e = e + 2 else out[#out + 1] = c; e = e + 1 end
    end
    pos = e + 1
    return table.concat(out)
  end
  val = function()
    ws()
    local c = s:sub(pos, pos)
    if c == '{' then
      local t = {}; pos = pos + 1; ws()
      if s:sub(pos, pos) == '}' then pos = pos + 1; return t end
      while true do
        ws(); local k = str(); ws(); pos = pos + 1
        t[k] = val(); ws()
        local d = s:sub(pos, pos); pos = pos + 1
        if d == '}' then return t end
      end
    elseif c == '[' then
      local t = {}; pos = pos + 1; ws()
      if s:sub(pos, pos) == ']' then pos = pos + 1; return t end
      while true do
        t[#t + 1] = val(); ws()
        local d = s:sub(pos, pos); pos = pos + 1
        if d == ']' then return t end
      end
    elseif c == '"' then return str()
    elseif s:sub(pos, pos + 3) == 'true' then pos = pos + 4; return true
    elseif s:sub(pos, pos + 4) == 'false' then pos = pos + 5; return false
    elseif s:sub(pos, pos + 3) == 'null' then pos = pos + 4; return nil
    else
      local e = s:find('[,%]}]', pos)
      local n = tonumber(s:sub(pos, e - 1)); pos = e; return n
    end
  end
  return val()
end
function log(l, tag, msg) if l ~= 'I' then print(l, tag, msg) end end
function vec3(x, y, z) return { x = x, y = y, z = z } end
local objs, nextId, counts = {}, 1, { made = 0, deleted = 0, reload = 0, swaps = 0, hiddenFar = 0 }
local Obj = {}
Obj.__index = Obj
function Obj:setField(k, _, v) self.f[k] = v end
function Obj:getField(k) return self.f[k] end
function Obj:setPosition(p) self.pos = p end
function Obj:setPosRot(x, y, z) self.pos = vec3(x, y, z) end
function Obj:setScale() end
function Obj:registerObject(name) self.name = name end
function Obj:getID() return self.id end
function Obj:delete() objs[self.id] = nil; counts.deleted = counts.deleted + 1 end
function Obj:setHidden(h) self.hidden = h end
function Obj:addObject() end
function Obj:postApply() counts.swaps = counts.swaps + 1 end
function createObject(cls) local o = setmetatable({ id = nextId, cls = cls, f = {} }, Obj); objs[nextId] = o; nextId = nextId + 1; counts.made = counts.made + 1; return o end
local tb = createObject('TerrainBlock')
scenetree = { MissionGroup = tb, findObject = function(n) if n == 'theTerrain' then return tb end
  if n:find('-') then return createObject('TerrainMaterial') end return nil end,
  findObjectById = function(id) return objs[id] end, findClassObjects = function() return {} end }
be = { reloadCollision = function() counts.reload = counts.reload + 1 end }
FS = { directoryExists = function() return true end, directoryCreate = function() end,
       fileExists = function(_, p) local f = realOpen(mapPath(p)); if f then f:close() return true end return false end,
       removeFile = function(_, p) os.remove(mapPath(p)) end }
os.execute('mkdir -p "' .. root .. '/temp/ticino"')
local car = { x = 0, y = 0 }
function getPlayerVehicle() return { getPosition = function() return vec3(car.x, car.y, 0) end } end
local paused = false
simTimeAuthority = { pause = function(p) paused = p end, getPause = function() return paused end }

-- ---- the run
if os.getenv('PROF') then dofile(os.getenv('PROF')) end
local stream = require('ticino/stream')
stream.PERF_FILE = '/ticino_perf_sim.csv'   -- (root/temp/ticino_perf_sim.csv)
-- start at the default spawn (Magliaso), drive west-north-west at 120 km/h
car.x, car.y = 747, -1094
stream.onClientPostStartMission('/levels/ticino/main.level.json')
local dt = 1 / 60
local v = 120 / 3.6
local dir = { -0.94, 0.34 }
local worstLua, t = 0, 0
local frames = 0
while t < seconds do
  local c0 = os.clock()
  stream.onUpdate(dt, dt)
  local ms = (os.clock() - c0) * 1000
  frames = frames + 1
  if frames > 3 then worstLua = math.max(worstLua, ms) end
  if os.getenv("PROF") and frames > 3 and ms > 10 then print(string.format("frame %d: %.1f ms", frames, ms)) end
  if not paused then car.x, car.y = car.x + dir[1] * v * dt, car.y + dir[2] * v * dt; t = t + dt end
end
local s = stream.status()
local live = 0
for _ in pairs(objs) do live = live + 1 end
print(string.format('drove %.1f km in %.0f s: %d window swaps, %d collision rebuilds, objects made %d deleted %d, in scene %d (%d colliders, %d far)',
  v * seconds / 1000, seconds, counts.swaps, counts.reload, counts.made, counts.deleted, live, s.objects.colliders, s.objects.far))
print(string.format('worst Lua frame after the start %.1f ms (luajit CPU; budget %d + %d ms); window now at tile (%d, %d), car tile (%d, %d)',
  worstLua, stream.BUDGET_MS, stream.OBJ_BUDGET_MS, s.window[1] / 256, s.window[2] / 256, s.cell[1], s.cell[2]))
