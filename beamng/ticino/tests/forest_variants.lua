-- forest.lua's shape variants outside the game: path spellings and the variant of a tile.
--   python tests/luajit.py tests/forest_variants.lua
local here = arg[0]:gsub('[^/]*$', '')
package.path = here .. '../mod/lua/ge/extensions/?.lua;' .. package.path
package.loaded['ticino/files'] = {}
local forest = require('ticino/forest')
assert(forest._variantPath('/levels/a/trees/oak.dae', 0) == '/levels/a/trees/oak.dae')
assert(forest._variantPath('/levels/a/trees/oak.dae', 2) == '/levels/a/trees/././oak.dae')
forest.SHAPE_VARIANTS = 1
assert(forest._variantOf('5_7') == 0)
forest.SHAPE_VARIANTS, forest.BLOCK = 4, 3
assert(forest._variantOf('3_3') == forest._variantOf('5_5'), 'one block, one variant')
local seen = {}
for x = -6, 6 do for y = -6, 6 do local v = forest._variantOf(x .. '_' .. y); assert(v >= 0 and v < 4); seen[v] = true end end
assert(seen[0] and seen[1] and seen[2] and seen[3], 'every variant used')
assert(forest._variantOf('0_0') ~= forest._variantOf('3_0') and forest._variantOf('0_0') ~= forest._variantOf('0_3'),
  'neighbouring blocks differ')
print('forest variants ok')
