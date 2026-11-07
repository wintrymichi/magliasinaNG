-- pace.lua outside the game: the gate keeps scene-changing frames apart, the pacer evens frames, and an emulation of
-- the engine's smoothed frame time (median of 3, then a slow average) shows the game-speed swings with and without
-- the gate for a queue of near-object bursts like the PC flight of 2026-10-31 (8 bursts of 125-483 ms in 1.6 s).
--   python tests/luajit.py tests/pace_test.lua
local here = arg[0]:gsub('[^/]*$', '')
package.path = here .. '../mod/lua/ge/extensions/?.lua;' .. package.path
local pace = require('ticino/pace')

local fails = 0
local function check(ok, what)
  print((ok and 'ok   ' or 'FAIL ') .. what)
  if not ok then fails = fails + 1 end
end

-- the engine's frame-time filter as described by BeamNG.Earth (design 5.1): median of the last 3 frames, then an EMA
local function newFilter()
  return { w = {}, ema = nil }
end
local function filt(f, ms)
  table.insert(f.w, 1, ms)
  if #f.w > 3 then f.w[4] = nil end
  local s = { unpack(f.w) }
  table.sort(s)
  local med = s[math.floor((#s + 1) / 2)]
  f.ema = f.ema and (f.ema + (med - f.ema) * 0.2) or med
  return f.ema
end

-- run `frames` frames of a queue of `jobs` bursts; every burst frame costs spike ms (+ half of it in the next frame,
-- the engine's deferred work), every frame base ms. gated: ask the gate first.
local function run(gated, jobs, base, spike, defer)
  local g = pace.newGate()
  local f = newFilter()
  local last = nil
  local deferred = 0
  local warp, slowRuns, run_ = 0, 0, 0
  local real, game = 0, 0
  local maxSpeed, minSpeed = 0, 1e9
  local dev, nDev = 0, 0
  local window = {}
  local done = 0
  for i = 1, 600 do
    g:beginFrame(last, false)
    local ms = base + deferred
    deferred = 0
    if jobs > 0 and (not gated or g:open()) then
      g:worked()
      jobs = jobs - 1
      done = done + 1
      ms = ms + spike
      deferred = spike * defer
    end
    last = ms
    local sim = filt(f, ms)
    real, game = real + ms, game + sim
    window[#window + 1] = { ms, sim }
    -- game speed over ~250 ms windows
    local wr, wg = 0, 0
    for k = #window, 1, -1 do
      wr, wg = wr + window[k][1], wg + window[k][2]
      if wr >= 250 then break end
    end
    if wr >= 250 then
      local sp = wg / wr
      maxSpeed, minSpeed = math.max(maxSpeed, sp), math.min(minSpeed, sp)
      dev, nDev = dev + math.abs(sp - 1), nDev + 1
    end
    if ms > base * 3 then run_ = run_ + 1 else
      if run_ >= 2 then slowRuns = slowRuns + 1 end
      run_ = 0
    end
  end
  return { done = done, slowRuns = slowRuns, maxSpeed = maxSpeed, minSpeed = minSpeed, dev = dev / nDev }
end

for _, defer in ipairs({ 0, 0.5 }) do
  local a = run(false, 8, 11, 150, defer)
  local b = run(true, 8, 11, 150, defer)
  for _, r in ipairs({ { 'without the gate', a }, { 'with the gate   ', b } }) do
    print(string.format('engine share next frame %.1f, %s: %d bursts, game speed %.2f..%.2f x, mean |speed - 1| %.3f',
      defer, r[1], r[2].done, r[2].minSpeed, r[2].maxSpeed, r[2].dev))
  end
  check(b.done == 8, 'the gate lets every burst through')
  check(b.dev < a.dev, 'smaller game-speed error with the gate')
  check(b.maxSpeed - b.minSpeed < a.maxSpeed - a.minSpeed, 'smaller game-speed swing with the gate')
end

-- gate rules
do
  local g = pace.newGate()
  for i = 1, 70 do g:beginFrame(10, false) end
  check(g:open(), 'open after calm frames')
  g:worked()
  check(not g:open(), 'one scene-changing step a frame (SAME_FRAME false)')
  g:beginFrame(200, false)
  check(not g:open(), 'closed the frame after a scene change')
  g:beginFrame(60, false)
  check(not g:open(), 'closed while the frames are slow')
  g:beginFrame(10, false); g:beginFrame(10, false)
  check(g:open(), 'open after two calm frames')
  g:worked()
  g:beginFrame(10, true)
  check(g:open(), 'always open while paused')
  -- a PC that never has calm frames: the timeout opens it
  local h = pace.newGate()
  for i = 1, 10 do h:beginFrame(10, false) end
  h:worked()
  local opened = false
  for i = 1, pace.CALM_TIMEOUT + 5 do
    h:beginFrame(i % 2 == 0 and 50 or 10, false)
    if h:open() then opened = true; break end
  end
  check(opened, 'the timeout opens a gate that never sees calm frames')
end

-- pacer
do
  local p = pace.newPacer()
  local waits = 0
  for i = 1, 200 do
    local ms = 8 + (i * 7 % 5)
    if p:step(ms) > 0 then waits = waits + 1 end
  end
  check(waits > 100, 'the pacer evens frames shorter than its target')
  local q = pace.newPacer()
  local any = false
  for i = 1, 200 do if q:step(45) > 0 then any = true end end
  check(not any, 'no pacing below 30 fps')
end

print(fails == 0 and 'all ok' or (fails .. ' failed'))
if fails > 0 then error('pace_test failed') end
