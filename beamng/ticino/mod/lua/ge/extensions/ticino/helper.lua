-- Ticino streaming: the optional helper process beside the game (beamng/ticino/helper/ticino_helper.py).
-- The helper puts the terrain window (.ter) and its combined base colour map together from the same blocks with
-- numpy, on another core, before the streamer needs them. Files only, in /temp/ticino/helper/ (the user folder):
--   alive.json        written by the helper every second; the helper is used only while it is fresh (ALIVE_S)
--   req.json          written here every REQ_EVERY_MS: the car, the window, the follow places, a jump window
--   r_<wx>_<wy>.json  a ready window: {"ter": path, "base": path}; take() deletes it, the streamer later the files
-- Without the helper (not started, stopped, too slow) everything stays as before: stream.lua makes the files itself.

local M = {}

M.DIR = '/temp/ticino/helper/'
M.ALIVE_S = 4              -- alive.json older than this: no helper
M.CHECK_EVERY_MS = 1000    -- how often alive.json is read
M.REQ_EVERY_MS = 250

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
  local dec = rawget(_G, 'jsonDecode')
  if not dec then return nil end
  local ok, t = pcall(dec, s)
  return ok and type(t) == 'table' and t or nil
end

local function exists(p)
  if FS and FS.fileExists then return FS:fileExists(p) end
  local f = io.open(p, 'rb')
  if f then f:close() return true end
  return false
end

function M.init(cfg, clock)
  S = { cfg = cfg, clock = clock, lastCheck = -1e9, on = false, lastReq = -1e9, taken = 0, missed = 0, waitMs = 0 }
  M.alive(true)
  return S.on
end

function M.stop() S = nil end

-- Is the helper running? (alive.json fresh). Read at most every CHECK_EVERY_MS unless force.
function M.alive(force)
  if not S then return false end
  local now = S.clock()
  if not force and now - S.lastCheck < M.CHECK_EVERY_MS then return S.on end
  S.lastCheck = now
  local a = decode(readAll(M.DIR .. 'alive.json'))
  local on = a and a.t and math.abs(os.time() - a.t) <= M.ALIVE_S or false
  S.info = on and a or nil
  if on ~= S.on then
    log('I', 'ticino', on and ('helper process found (pid ' .. tostring(a.pid) .. ')') or 'no helper process')
  end
  S.on = on
  return on
end

-- Tell the helper where the car is (x, y game metres), which window it is in (samples) and, at a jump, the window
-- that has to come first. lo/hi: stream.lua's follow places, n tiles a side.
function M.request(x, y, window, lo, hi, n, jumpWindow)
  if not S then return end
  local now = S.clock()
  local vx, vy = 0, 0
  if S.px and now > S.pt then
    local dt = (now - S.pt) / 1000
    vx, vy = (x - S.px) / dt, (y - S.py) / dt
  end
  if jumpWindow then vx, vy = 0, 0 end
  S.px, S.py, S.pt = x, y, now
  S.lastReq = now
  local c = S.cfg
  local s = string.format('{"x":%.2f,"y":%.2f,"vx":%.2f,"vy":%.2f,"wx":%d,"wy":%d,"cell":%d,"n":%d,"lo":%d,"hi":%d,'
    .. '"ox":%.3f,"oy":%.3f,"square":%.4f%s}', x, y, vx, vy, window[1], window[2], c.cell, n, lo, hi,
    c.origin[1], c.origin[2], c.square,
    jumpWindow and string.format(',"jump":[%d,%d]', jumpWindow[1], jumpWindow[2]) or '')
  local f = io.open(M.DIR .. 'req.json', 'wb')
  if f then f:write(s); f:close() end
end

-- Every frame: a request every REQ_EVERY_MS while the helper runs.
function M.tick(x, y, window, lo, hi, n)
  if not S or not M.alive() then return end
  if S.clock() - S.lastReq >= M.REQ_EVERY_MS then M.request(x, y, window, lo, hi, n) end
end

-- The helper's files of window (wx, wy) if they are ready: { ter = path, base = path }, and the window is the
-- streamer's from now on (its manifest is deleted, the streamer deletes the files when it is done with them).
function M.take(wx, wy)
  if not S or not S.on then return nil end
  local mp = M.DIR .. 'r_' .. wx .. '_' .. wy .. '.json'
  local m = decode(readAll(mp))
  if not m or not m.ter or not exists(m.ter) or (m.base and not exists(m.base)) then return nil end
  if FS and FS.removeFile then pcall(function() FS:removeFile(mp) end) else os.remove(mp) end
  S.taken = S.taken + 1
  return m
end

-- At a jump (the game paused): wait up to ms for the helper's window. True when it is there.
function M.wait(wx, wy, ms)
  if not S or not M.alive(true) then return false end
  local t0 = S.clock()
  local mp = M.DIR .. 'r_' .. wx .. '_' .. wy .. '.json'
  while S.clock() - t0 < ms do
    if exists(mp) then
      S.waitMs = S.clock() - t0
      return true
    end
    local t1 = os.clock()
    while os.clock() - t1 < 0.005 do end   -- no sleep in the game's Lua: the helper works on another core
  end
  S.missed = S.missed + 1
  S.waitMs = S.clock() - t0
  log('W', 'ticino', string.format('helper: window %d,%d not ready after %d ms, made in Lua', wx, wy, ms))
  return false
end

-- The helper's alive.json while it runs (the Ticino server adds serve = true and root), else nil.
function M.info() return S and S.info end

function M.stats()
  if not S then return 'off' end
  return { on = S.on, taken = S.taken, missed = S.missed, lastWaitMs = S.waitMs }
end

return M
