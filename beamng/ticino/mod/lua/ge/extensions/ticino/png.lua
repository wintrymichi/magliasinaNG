-- Ticino streaming: an uncompressed RGB PNG writer (stored deflate blocks), for the window's base colour maps.
-- Pure Lua (LuaJIT's bit library), no game API: tests/test_lua.py checks its files with PIL.
-- parts(rows, w, h, yield) takes the image rows (strings of w * 3 bytes, top row first) and returns the file as a list
-- of strings, written one by one (terwin.writeParts): no 800 kB string is ever joined. Each stored deflate block holds
-- whole rows. yield (optional) is called every few rows, for running inside a coroutine.

local bit = require('bit')
local band, bxor, rshift = bit.band, bit.bxor, bit.rshift
local byte, char, concat = string.byte, string.char, table.concat

local M = {}

local CRC = {}
for i = 0, 255 do
  local c = i
  for _ = 1, 8 do
    if band(c, 1) == 1 then c = bxor(0xEDB88320, rshift(c, 1)) else c = rshift(c, 1) end
  end
  CRC[i] = c
end

local function crcUpdate(crc, s)
  for i = 1, #s do
    crc = bxor(CRC[band(bxor(crc, byte(s, i)), 0xFF)], rshift(crc, 8))
  end
  return crc
end

local function crcFinal(crc)
  crc = bxor(crc, 0xFFFFFFFF)
  if crc < 0 then crc = crc + 4294967296 end
  return crc
end

local function u32(v)
  v = v % 4294967296
  return char(band(rshift(v, 24), 0xFF), band(rshift(v, 16), 0xFF), band(rshift(v, 8), 0xFF), band(v, 0xFF))
end

local function chunk(kind, data)
  return u32(#data) .. kind .. data .. u32(crcFinal(crcUpdate(crcUpdate(0xFFFFFFFF, kind), data)))
end

function M.crc32(s) return crcFinal(crcUpdate(0xFFFFFFFF, s)) end

function M.parts(rows, w, h, yield)
  local rowLen = w * 3 + 1
  local perBlock = math.max(1, math.floor(65535 / rowLen))
  local nBlocks = math.ceil(h / perBlock)
  local idatLen = 2 + nBlocks * 5 + h * rowLen + 4
  local out = { '\137PNG\r\n\26\n', chunk('IHDR', u32(w) .. u32(h) .. char(8, 2, 0, 0, 0)), u32(idatLen) .. 'IDAT' }
  local crc = crcUpdate(0xFFFFFFFF, 'IDAT')
  local function put(s)
    out[#out + 1] = s
    crc = crcUpdate(crc, s)
  end
  put(char(0x78, 0x01))
  local a, b = 1, 0                                  -- adler32 of the raw image
  local r = 1
  for blk = 1, nBlocks do
    local k = math.min(perBlock, h - r + 1)
    local len = k * rowLen
    local nlen = 65535 - len
    put(char(blk == nBlocks and 1 or 0, band(len, 0xFF), rshift(len, 8), band(nlen, 0xFF), rshift(nlen, 8)))
    for _ = 1, k do
      local row = rows[r]
      assert(#row == w * 3, 'png: row ' .. r .. ' is ' .. #row .. ' bytes, not ' .. w * 3)
      put('\0')
      put(row)
      b = (b + a) % 65521                            -- the filter byte (0) adds a to b only
      for i = 1, #row do
        a = a + byte(row, i)
        b = b + a
      end
      a, b = a % 65521, b % 65521
      r = r + 1
      if yield and r % 16 == 0 then yield() end
    end
  end
  put(u32(b * 65536 + a))
  out[#out + 1] = u32(crcFinal(crc))
  out[#out + 1] = chunk('IEND', '')
  return out
end

function M.write(rows, w, h, yield)
  return concat(M.parts(rows, w, h, yield))
end

return M
