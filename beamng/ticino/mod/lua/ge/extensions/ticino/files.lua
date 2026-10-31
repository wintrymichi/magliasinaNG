-- Ticino streaming: where the streamed files of the zones come from.
-- Packs in mods (as before): /levels/ticino/..., every tile is there at once.
-- Ticino server (beamng/ticino/server/ticino_server.py) running and the zone packs NOT in mods: the server puts the
-- files of the tiles round the car into /temp/ticino/srv/ (shapes as .cdae, the tile files already point at them) and
-- lists the tiles it has finished in /temp/ticino/helper/ready.json:
--   {"gen": n, "root": "/temp/ticino/srv/", "near": [tile keys], "far": [tile keys]}
-- A near tile is its objects, trees, collision cells and far tile; a far tile only the far ground. A tile the server
-- has not finished is skipped and marked late; when ready.json lists new tiles the streamer asks again (refresh).

local M = {}

M.DIR = '/temp/ticino/helper/'
M.LEVEL_ROOT = '/levels/ticino/'
M.READ_EVERY_MS = 200
M.REFRESH_MIN_MS = 1000    -- the streamer asks again at most this often (each ask may queue a collision rebuild)
M.SETTLE_MS = 2500         -- tiles that came are asked for together once none came for this long ...
M.SETTLE_MAX_MS = 8000     -- ... or this long after the first of them (standing in Lugano, the server finished tiles
                           -- one by one for minutes and every ask re-queued objects, trees and a collision rebuild)
M.URGENT_RING = 1          -- a tile this close to the car's is asked for at once
M.WAIT_STEP_S = 0.005
M.START_MS = 30000         -- late tiles in the first this many ms are the start's (stats)

local S = nil

local function readAll(p)
  local f = io.open(p, 'rb')
  if not f then return nil end
  local s = f:read('*a')
  f:close()
  return s
end

local function decode(s)
  if not s or s == '' then return nil end
  local ok, t = pcall(jsonDecode, s)
  return ok and type(t) == 'table' and t or nil
end

local function exists(p)
  if FS and FS.fileExists then return FS:fileExists(p) end
  local f = io.open(p, 'rb')
  if f then f:close() return true end
  return false
end

-- cfg: stream.json; clock: ms; info: the helper's alive.json (helper.info()) or nil
function M.init(cfg, clock, info)
  S = { serving = false, root = M.LEVEL_ROOT, near = {}, far = {}, gen = -1, last = -1e9, clock = clock,
        lateNear = {}, lateFar = {}, came = {}, cameN = 0, cameFirst = 0, cameLast = 0, lateN = 0, lateRun = 0, refreshes = 0, lastRefresh = -1e9, t0 = clock() }
  S.tileM = cfg.cell * cfg.square
  -- the packs are in mods if any zone's slice.json is there (a test install may hold only some zones)
  local inPacks = #(cfg.zones or {}) == 0
  for _, z in ipairs(cfg.zones or {}) do
    if exists(M.LEVEL_ROOT .. 'z/' .. z .. '/slice.json') then inPacks = true; break end
  end
  if not inPacks and info and info.serve then
    S.serving = true
    S.root = info.root or '/temp/ticino/srv/'
    M.poll(true)
    log('I', 'ticino', 'zone files from the Ticino server (' .. S.root .. '), ' .. #(S.nearList or {}) .. ' tiles ready')
  elseif not inPacks then
    log('E', 'ticino', 'the zone packs are neither in mods nor served: start the Ticino server (ticino_server) '
      .. 'or put the ticino_<zone> zips into mods')
  end
  return S.serving
end

function M.stop() S = nil end

function M.serving() return S ~= nil and S.serving end

-- A game path of the level, as the streamer should read it now.
function M.map(p)
  if S and S.serving and p:sub(1, #M.LEVEL_ROOT) == M.LEVEL_ROOT then return S.root .. p:sub(#M.LEVEL_ROOT + 1) end
  return p
end

-- May tile key's objects, trees and collision cells be loaded now? (always, unless served and not ready: late)
function M.near(key)
  if not (S and S.serving) then return true end
  if S.near[key] then return true end
  if not S.lateNear[key] then
    S.lateNear[key] = true
    S.lateN = S.lateN + 1
    if S.clock() - S.t0 > M.START_MS then S.lateRun = S.lateRun + 1 end    -- late while driving, not at the start
  end
  return false
end

-- The same without marking the tile late (prefetching).
function M.ready(key)
  return not (S and S.serving) or S.near[key] or false
end

-- May the far ground of tile key be loaded now?
function M.far(key)
  if not (S and S.serving) then return true end
  if S.far[key] then return true end
  S.lateFar[key] = true
  return false
end

-- The tile key of a collision cell (i, j) of cell metres.
function M.colTile(i, j, cell)
  local per = math.floor(S.tileM / cell + 0.5)
  return math.floor(i / per) .. '_' .. math.floor(j / per)
end

local function toSet(list)
  local s = {}
  for _, k in ipairs(list or {}) do s[k] = true end
  return s
end

-- Read ready.json (every READ_EVERY_MS unless force). Returns nearCame, farCame, ring: true when tiles the streamer had
-- to skip are there now; it then asks again for what it skipped. Near tiles that came are held back until none came
-- for SETTLE_MS (at most SETTLE_MAX_MS), unless one is within URGENT_RING of the car's tile (cx, cy); ring is the
-- distance of the nearest of them from (cx, cy) (the streamer leaves out the collision when it is far).
function M.poll(force, cx, cy)
  if not (S and S.serving) then return false, false end
  local now = S.clock()
  if not force and now - S.last < M.READ_EVERY_MS then return false, false end
  S.last = now
  local r = decode(readAll(M.DIR .. 'ready.json'))
  if r and r.gen ~= S.gen then
    S.gen = r.gen
    S.near, S.far, S.nearList = toSet(r.near), toSet(r.far), r.near
  end
  if force then return false, false end
  for k in pairs(S.lateNear) do
    if S.near[k] then
      S.lateNear[k] = nil
      if S.cameN == 0 then S.cameFirst = now end
      S.came[k] = true; S.cameN = S.cameN + 1; S.cameLast = now
    end
  end
  local farCame = false
  for k in pairs(S.lateFar) do
    if S.far[k] then farCame = true; S.lateFar[k] = nil end
  end
  if now - S.lastRefresh < M.REFRESH_MIN_MS then
    if farCame then S.farPending = true end
    return false, false
  end
  local nearCame, ring = false, nil
  if S.cameN > 0 then
    for k in pairs(S.came) do
      local tx, ty = k:match('^(-?%d+)_(-?%d+)$')
      if tx and cx then
        local d = math.max(math.abs(tonumber(tx) - cx), math.abs(tonumber(ty) - cy))
        if not ring or d < ring then ring = d end
      end
    end
    if (ring and ring <= M.URGENT_RING) or now - S.cameLast >= M.SETTLE_MS or now - S.cameFirst >= M.SETTLE_MAX_MS then
      nearCame = true
      S.came, S.cameN = {}, 0
    end
  end
  farCame = farCame or S.farPending or false
  if nearCame or farCame then
    S.farPending = nil
    S.lastRefresh = now
    S.refreshes = S.refreshes + 1
  end
  return nearCame, farCame, ring
end

-- At a jump (the game paused): wait up to ms for the near tiles within R of (cx, cy) that the level has (has: the
-- stream.json tiles). Returns the ms waited.
function M.waitNear(cx, cy, R, has, ms)
  if not (S and S.serving) then return 0 end
  local t0 = S.clock()
  while true do
    M.poll(true)
    local missing = 0
    for ty = cy - R, cy + R do
      for tx = cx - R, cx + R do
        local k = tx .. '_' .. ty
        if has[k] and not S.near[k] then missing = missing + 1 end
      end
    end
    local waited = S.clock() - t0
    if missing == 0 then return waited end
    if waited > ms then
      log('W', 'ticino', string.format('server: %d tiles round the car not ready after %d ms', missing, ms))
      return waited
    end
    local t1 = os.clock()
    while os.clock() - t1 < M.WAIT_STEP_S do end      -- no sleep in the game's Lua: the server works beside it
  end
end

function M.stats()
  if not S then return 'off' end
  if not S.serving then return 'packs' end
  local n = 0
  for _ in pairs(S.near) do n = n + 1 end
  return { serving = true, gen = S.gen, near = n, late = S.lateN, lateRun = S.lateRun, refreshes = S.refreshes }
end

return M
