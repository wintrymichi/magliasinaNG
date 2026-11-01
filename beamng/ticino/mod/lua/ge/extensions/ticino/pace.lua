-- Ticino frame pacing (required by stream.lua; pure Lua but for sleep(), runs under plain luajit: tests/pace_test.lua).
--
-- Why (BeamNG.Earth governor.lua / framepacer.lua, (c) 2026 TecnaGamer, MIT licence, see mod/THIRD_PARTY.md): the
-- engine moves the world by a SMOOTHED frame time (a clamp, the median of the last 3 frames and a slow average), not
-- by the real gap between frames. One lone slow frame is dropped by the median (a hitch, but the game speed stays
-- right); two or more slow frames in a row, or slow-fast-slow, pass the median and drag the average: the game runs
-- slow and then fast, which reads as a stutter even at a high mean fps. The PC flights of 2026-10-31 had exactly that:
-- 8 "near objects" bursts in 1.6 s, one a frame, each 125-483 ms (the engine's work for what the burst added lands in
-- the same and the next frame).
--
-- 1. The gate (Earth's heavy slots): a frame that changes the scene (a burst of objects, a forest pass, collision
--    cells, a collision rebuild, a terrain swap) may run only when the QUIET frames before it changed nothing and
--    were calm (no longer than the median frame + a margin): every such frame stays a lone spike between calm ones,
--    the one kind the engine's filter drops. A gate that waited CALM_TIMEOUT frames opens anyway (a slow PC never
--    has calm frames). Off while the game is paused (a jump: no game time to warp).
-- 2. The pacer (Earth's framepacer.lua): a frame shorter than the target waits the rest just before it is drawn, the
--    target being the recent frames' PERCENTILE: most frames come at the same spacing. It costs a little fps (Earth:
--    up to a tenth). Off below 30 fps, while paused, and with "pacing": false in settings/ticino.json.

local M = {}

-- the gate
M.QUIET = 2                -- frames that change nothing before (and so after) a scene-changing frame
M.CALM_MARGIN_MS = 2.0     -- a calm frame is no longer than the median frame + max(this, CALM_SHARE x median)
M.CALM_SHARE = 0.25
M.CALM_TIMEOUT = 30        -- frames a waiting gate holds at most
M.BASE_FRAMES = 64         -- the median of this many frames that changed nothing
M.SAME_FRAME = false       -- may a second scene-changing step run in a frame that changed the scene already?
-- the pacer
M.WINDOW = 120             -- frames the target is taken over (~1-2 s)
M.EVERY = 30               -- frames between recomputes
M.PERCENTILE = 0.70
M.TARGET_ALPHA = 0.25
M.MIN_MS, M.MAX_MS = 4.0, 33.4
M.MIN_WAIT_MS = 0.3

local floor, min, max = math.floor, math.min, math.max

local function median(t, n)
  local s = {}
  for i = 1, n do s[i] = t[i] end
  table.sort(s)
  if n == 0 then return nil end
  if n % 2 == 1 then return s[(n + 1) / 2] end
  return 0.5 * (s[n / 2] + s[n / 2 + 1])
end

-- ------------------------------------------------------------------ the gate
local G = {}
G.__index = G

function M.newGate()
  return setmetatable({ frame = 0, lastWork = -1e9, waitSince = nil, hist = {}, histN = 0, base = nil,
                        w = {}, workedPrev = false, workedNow = false,
                        stats = { opened = 0, timeouts = 0, waited = 0 } }, G)
end

-- once a frame, first: ms = the wall time of the frame that just ended, paused = the game is paused
function G:beginFrame(ms, paused)
  if ms and not self.workedNow and self.frame - self.lastWork > 1 then   -- a frame with no work and none just before
    self.histN = self.histN + 1
    self.hist[(self.histN - 1) % M.BASE_FRAMES + 1] = ms
    self.base = median(self.hist, min(self.histN, M.BASE_FRAMES))
  end
  -- the walls of the last QUIET frames, newest first
  table.insert(self.w, 1, ms or 0)
  if #self.w > M.QUIET then self.w[#self.w] = nil end
  self.frame = self.frame + 1
  self.workedNow = false
  self.paused = paused and true or false
end

function G:calm()
  if not self.base or #self.w < M.QUIET then return false end
  local lim = self.base + max(M.CALM_MARGIN_MS, M.CALM_SHARE * self.base)
  for i = 1, M.QUIET do
    if (self.w[i] or 1e9) > lim then return false end
  end
  return true
end

-- May a scene-changing step run in this frame? (Then the caller runs it and calls worked().)
function G:open()
  if self.paused then return true end
  -- one scene-changing step a frame: letting more in once a frame had worked piled cells, near objects and forest
  -- into the same frame (PC 2026-11-01: 2-3 gate frames of 400-550 ms instead of 8-9 smaller ones)
  if self.workedNow then return M.SAME_FRAME end
  if self.frame - self.lastWork <= M.QUIET then return false end
  self.waitSince = self.waitSince or self.frame
  if self:calm() then return true end
  if self.frame - self.waitSince >= M.CALM_TIMEOUT then
    self.stats.timeouts = self.stats.timeouts + 1
    return true
  end
  self.stats.waited = self.stats.waited + 1
  return false
end

-- The step ran (it changed the scene in this frame).
function G:worked()
  if not self.workedNow then self.stats.opened = self.stats.opened + 1 end
  self.workedNow, self.lastWork, self.waitSince = true, self.frame, nil
end

function G:snapshot()
  return { base = self.base, frame = self.frame, opened = self.stats.opened, timeouts = self.stats.timeouts,
           waited = self.stats.waited }
end

-- ------------------------------------------------------------------ the pacer
local P = {}
P.__index = P

function M.newPacer()
  return setmetatable({ ring = {}, n = 0, head = 0, target = nil, since = 0, slept = 0 }, P)
end

function P:reset()
  self.ring, self.n, self.head, self.target, self.since = {}, 0, 0, nil, 0
end

local function percentile(ring, n, p)
  local t = {}
  for i = 1, n do t[i] = ring[i] end
  table.sort(t)
  return t[max(1, min(n, floor(n * p + 0.5)))]
end

-- One frame's own time (ms, without the wait): the wait (ms) to add, 0 for none.
function P:step(frameMs)
  if not frameMs or frameMs <= 0 then return 0 end
  self.head = self.head % M.WINDOW + 1
  self.ring[self.head] = frameMs
  self.n = min(self.n + 1, M.WINDOW)
  self.since = self.since + 1
  if self.n >= M.EVERY and self.since >= M.EVERY then
    self.since = 0
    local p = percentile(self.ring, self.n, M.PERCENTILE)
    if p > M.MAX_MS then
      self.target = nil                 -- slower than 30 fps: pacing would only cost frames
    else
      p = max(M.MIN_MS, p)
      self.target = self.target and (self.target + (p - self.target) * M.TARGET_ALPHA) or p
    end
  end
  if not self.target then return 0 end
  local wait = self.target - frameMs
  return wait >= M.MIN_WAIT_MS and wait or 0
end

local socket = nil
function M.sleep(ms)
  if socket == nil then
    local ok, s = pcall(require, 'socket')
    socket = ok and type(s) == 'table' and s.sleep and s or false
  end
  if socket then socket.sleep(ms / 1000) end
  return socket and true or false
end

-- ------------------------------------------------------------------ engine metrics (slow-frame lines)
-- The engine's own subsystems of the frame that just ended, the n largest ("RenderShadows 210.3, ..."), or '' when
-- the game has no Engine.Debug.getLastPerformanceMetrics. (Earth core.lua noteHitch: tells a GpuCull, shadow or
-- texture hitch from the Lua's.)
local metrics = {}
function M.engineTop(n)
  local dbg = rawget(_G, 'Engine') and Engine.Debug
  if not (dbg and dbg.getLastPerformanceMetrics) then return '' end
  for k in pairs(metrics) do metrics[k] = nil end
  if not pcall(dbg.getLastPerformanceMetrics, metrics) then return '' end
  local arr = {}
  for k, v in pairs(metrics) do
    if type(v) == 'number' and type(k) == 'string' and not k:find('^phys') and not k:find('^virt') then
      arr[#arr + 1] = { k, v }
    end
  end
  table.sort(arr, function(a, b) return a[2] > b[2] end)
  local out = {}
  for i = 1, min(n or 6, #arr) do out[#out + 1] = string.format('%s %.1f', arr[i][1], arr[i][2]) end
  return table.concat(out, ', ')
end

return M
