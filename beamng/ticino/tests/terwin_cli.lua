-- Outside the game: put a window together with terwin.lua and write its .ter and base PNGs (tests/test_lua.py
-- compares them with blocks.window_ter and the blocks' colour maps).
--   luajit terwin_cli.lua <level dir> <wx> <wy> <out dir>
package.path = arg[0]:gsub('[^/]*$', '') .. '../mod/lua/ge/extensions/?.lua;' .. package.path
local terwin = require('ticino/terwin')
local dir, wx, wy, out = arg[1], tonumber(arg[2]), tonumber(arg[3]), arg[4]
local f = assert(io.open(dir .. '/stream.json'))
local text = f:read('*a'); f:close()
-- the few fields needed, without a JSON library
local cfg = { materials = {}, baseTextures = {} }
for _, k in ipairs({ 'block', 'window', 'basePx' }) do cfg[k] = tonumber(text:match('"' .. k .. '":%s*(%d+)')) end
for m in text:match('"materials":%s*(%b[])'):gmatch('"([^"]+)"') do cfg.materials[#cfg.materials + 1] = m end
for m in text:match('"baseTextures":%s*(%b[])'):gmatch('"([^"]+)"') do cfg.baseTextures[#cfg.baseTextures + 1] = m end
local tc = terwin.newCache(dir .. '/blocks/terrain/', 16)
local bc = terwin.newCache(dir .. '/blocks/base/', 100)
local t0 = os.clock()
local ter = terwin.ter(tc, cfg, wx, wy, function() end)
local t1 = os.clock()
assert(terwin.writeFile(out .. '/w.ter', ter))
local tp = 0
for _, key in ipairs(cfg.baseTextures) do
  local a = os.clock()
  local png = terwin.basePng(bc, cfg, key, wx, wy, function() end)
  tp = tp + (os.clock() - a)
  assert(terwin.writeFile(out .. '/' .. key .. '.png', png))
end
print(string.format('ter %.0f ms, %d base PNGs %.0f ms (luajit, CPU)', (t1 - t0) * 1000, #cfg.baseTextures, tp * 1000))
