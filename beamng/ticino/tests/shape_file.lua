-- Outside the game: objects.lua takes the .cdae of a shape when it is installed and falls back to the .dae.
--   python tests/luajit.py tests/shape_file.lua
EXT = (arg and arg[0] or ''):gsub('[^/]*$', '') .. '../mod/lua/ge/extensions'
package.path = EXT .. '/?.lua;' .. package.path
function log() end
local files = { ['/l/z/a.cdae'] = true, ['/l/z/b.dae'] = true, ['/l/z/c.dae'] = true, ['/l/z/c.cdae'] = true }
FS = { fileExists = function(_, p) return files[p] == true end }
local M = require('ticino/objects')
M.init({}, 'ticino', nil)
local want = { ['/l/z/a.cdae'] = '/l/z/a.cdae', ['/l/z/a.dae'] = '/l/z/a.cdae', ['/l/z/b.cdae'] = '/l/z/b.dae',
  ['/l/z/b.dae'] = '/l/z/b.dae', ['/l/z/c.dae'] = '/l/z/c.cdae', ['/x/y.DAE'] = '/x/y.DAE' }
local bad = 0
for k, v in pairs(want) do
  local got = M.shapeFile(k)
  if got ~= v then print('WRONG', k, got, v); bad = bad + 1 end
end
print(bad == 0 and 'OK' or 'FAILED')
