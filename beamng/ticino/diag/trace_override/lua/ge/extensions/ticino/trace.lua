-- DIAGNOSTIC OVERRIDE (2026-10-29, thread "Far partire BeamNG con il Ticino completo"): the last 300 steps of the
-- streamer, rewritten to <user folder>/ticino_trace.txt after every step, so a freeze shows the call that never returned.
local M, ring, n = {}, {}, 0
local t0 = os.clock()
function M.t(msg)
  n = n + 1
  ring[#ring + 1] = string.format('%d %.3f %s', n, os.clock() - t0, msg)
  if #ring > 300 then table.remove(ring, 1) end
  local f = io.open('/ticino_trace.txt', 'wb')
  if f then f:write(table.concat(ring, '\n'), '\n'); f:close() end
end
return M
