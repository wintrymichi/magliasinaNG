-- The AI graph of the Ticino level, made at build time (beamng/ticino/aimap.py) and handed to the game's map.lua as
-- ready nodes: the level has no AI DecalRoads, so the game's own graph is empty until this one is loaded.
--
-- Why: map.lua builds its graph from the AI DecalRoads clipped to the terrain, and the terrain is only the 3 km window
-- round the car: every node outside it lay at z 0, findClosestRoad found nothing there, 4,020 of 4,065 signals failed
-- ("Map node could not be set") and traffic ran only near the spawn; map.reset over the 57,298 roads took 28-30 s.
--
-- File (aimap.py): b"TAIM", u32 version, u32 nodes, u32 edges, u32 types, nodes f32 x y z radius, edges u32 in, u32
-- out, u16 type, u16 flags (bit0 oneWay, bit1 gated), u32 length + json [[drivability, speedLimit, lanes], ...].

local ffi = require('ffi')

local M = {}

M.FILE = '/levels/ticino/ai/aimap.bin'

local function u32(s, o)
  local a, b, c, d = s:byte(o + 1, o + 4)
  return a + b * 256 + c * 65536 + d * 16777216
end

-- The file as plain Lua data: { n, m, pos = float array (x, y, z, r per node), ein, eout, etype, eflags, types }.
-- `data` is the file's bytes (a string); the arrays are copies, so the string may go.
function M.parse(data)
  if type(data) ~= 'string' or #data < 20 or data:sub(1, 4) ~= 'TAIM' then return nil, 'not an aimap file' end
  local ver, n, m, nt = u32(data, 4), u32(data, 8), u32(data, 12), u32(data, 16)
  if ver ~= 1 then return nil, 'aimap version ' .. ver end
  local o = 20
  local need = o + n * 16 + m * 12 + 4
  if #data < need then return nil, 'aimap file cut short' end
  local base = ffi.cast('const uint8_t *', data)
  local pos = ffi.new('float[?]', n * 4)
  ffi.copy(pos, base + o, n * 16)
  o = o + n * 16
  local ein, eout = ffi.new('uint32_t[?]', m), ffi.new('uint32_t[?]', m)
  local etype, eflags = ffi.new('uint16_t[?]', m), ffi.new('uint16_t[?]', m)
  local ep = ffi.cast('const uint8_t *', base + o)
  for k = 0, m - 1 do
    local q = ep + k * 12
    ein[k] = ffi.cast('const uint32_t *', q)[0]
    eout[k] = ffi.cast('const uint32_t *', q + 4)[0]
    etype[k] = ffi.cast('const uint16_t *', q + 8)[0]
    eflags[k] = ffi.cast('const uint16_t *', q + 10)[0]
  end
  o = o + m * 12
  local ln = u32(data, o)
  local types = (jsonDecode or require('json').decode)(data:sub(o + 5, o + 4 + ln))
  if type(types) ~= 'table' or #types ~= nt then return nil, 'aimap types unreadable' end
  return { n = n, m = m, pos = pos, ein = ein, eout = eout, etype = etype, eflags = eflags, types = types }
end

return M
