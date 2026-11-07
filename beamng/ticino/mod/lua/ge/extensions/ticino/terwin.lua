-- Ticino streaming: the terrain window and its base colour maps, put together from the zone's blocks.
-- No game API except file reading (io.open in the game resolves level paths, also inside the mod's zip):
-- tests/test_lua.sh runs it outside the game and compares the result with blocks.window_ter.
--
-- Blocks (beamng/ticino/blocks.py): blocks/terrain/t_<bx>_<by>.bin = B*B uint16 heights then B*B uint8 layers, rows
-- from the south; blocks/base/<key>_<bx>_<by>.rgb = (B/P)^2 RGB pixels, rows from the south. The window: W*W samples
-- from sample (wx, wy), as a version 9 .ter; its base maps W/P pixels a side, PNG rows from the NORTH.

local png = require('ticino/png')

local M = {}

local sub, rep, concat = string.sub, string.rep, table.concat

M.CACHE_BLOCKS = 16          -- blocks kept in memory (heights + layers, 4.9 MB each at 1280)

local function readAll(path)
  local f = io.open(path, 'rb')
  if not f then return nil end
  local s = f:read('*a')
  f:close()
  return s
end
M.readAll = readAll

-- A cache of block files: key -> string (nil when the block is missing: outside the zone)
local Cache = {}
Cache.__index = Cache

function M.newCache(dir, max)
  return setmetatable({ dir = dir, max = max or M.CACHE_BLOCKS, data = {}, order = {}, misses = 0 }, Cache)
end

function Cache:get(name)
  local d = self.data[name]
  if d ~= nil then return d or nil end
  self.misses = self.misses + 1
  d = readAll(self.dir .. name) or false
  self.data[name] = d
  self.order[#self.order + 1] = name
  while #self.order > self.max do
    local old = table.remove(self.order, 1)
    self.data[old] = nil
  end
  return d or nil
end

-- Rows of a W-wide window from sample origin (wx, wy): for each row r (0 = south), the byte string of the samples
-- wx .. wx + W - 1 of global row wy + r, from blocks of B samples whose row strings are `itemSize` bytes a sample,
-- starting at byte `offset` of the block file. fill: the bytes of one missing sample.
local function windowRows(cache, prefix, B, W, wx, wy, itemSize, offset, fill, rowOrder, yield)
  local out = {}
  local rowBytes = B * itemSize
  local nr = W
  for i = 0, nr - 1 do
    local r = rowOrder == 'north' and (nr - 1 - i) or i
    local gy = wy + r
    local by = math.floor(gy / B)
    local br = gy - by * B
    local parts = {}
    local c = 0
    while c < W do
      local gx = wx + c
      local bx = math.floor(gx / B)
      local bc = gx - bx * B
      local k = math.min(B - bc, W - c)
      local s = cache:get(prefix .. bx .. '_' .. by .. '.' .. (itemSize == 3 and 'rgb' or 'bin'))
      if s then
        local a = offset + br * rowBytes + bc * itemSize + 1
        parts[#parts + 1] = sub(s, a, a + k * itemSize - 1)
      else
        parts[#parts + 1] = rep(fill, k)
      end
      c = c + k
    end
    out[i + 1] = concat(parts)
    if yield and i % 128 == 127 then yield() end
  end
  return out
end

-- The window .ter (version 9) as a list of strings (written one by one: writeParts), or as one string (join).
function M.terParts(cache, cfg, wx, wy, yield)
  local B, W = cfg.block, cfg.window
  local parts = { string.char(9), string.char(W % 256, math.floor(W / 256) % 256, math.floor(W / 65536) % 256, 0) }
  for _, r in ipairs(windowRows(cache, 't_', B, W, wx, wy, 2, 0, '\0\0', 'south', yield)) do parts[#parts + 1] = r end
  for _, r in ipairs(windowRows(cache, 't_', B, W, wx, wy, 1, 2 * B * B, '\0', 'south', yield)) do parts[#parts + 1] = r end
  local mats = cfg.materials
  local n = #mats
  parts[#parts + 1] = string.char(n % 256, math.floor(n / 256) % 256, 0, 0)
  for _, m in ipairs(mats) do parts[#parts + 1] = string.char(#m) .. m end
  return parts
end

function M.ter(cache, cfg, wx, wy, yield)
  return concat(M.terParts(cache, cfg, wx, wy, yield))
end

-- The window's base colour map of texture `key` as PNG parts (rows from the north, as the level's maps).
function M.basePngParts(cache, cfg, key, wx, wy, yield)
  local P = cfg.basePx
  local B, W = cfg.block / P, cfg.window / P
  local rows = windowRows(cache, key .. '_', B, W, wx / P, wy / P, 3, 0, '\128\128\128', 'north', yield)
  return png.parts(rows, W, W, yield)
end

function M.basePng(cache, cfg, key, wx, wy, yield)
  return concat(M.basePngParts(cache, cfg, key, wx, wy, yield))
end

function M.writeFile(path, data)
  local f, err = io.open(path, 'wb')
  if not f then return false, err end
  f:write(data)
  f:close()
  return true
end

-- Write a list of strings to a file, calling yield between them (a 12 MB window in one write took ~40 ms).
function M.writeParts(path, parts, yield)
  local f, err = io.open(path, 'wb')
  if not f then return false, err end
  for i, p in ipairs(parts) do
    f:write(p)
    if yield and i % 64 == 0 then yield() end
  end
  f:close()
  return true
end

return M
