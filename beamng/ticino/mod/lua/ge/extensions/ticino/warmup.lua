-- Ticino warm-up (GE extension 'ticino_warmup', file ticino/warmup.lua: an underscore is a folder). Run it once inside
-- the level ticino after installing a new region, from the console:  extensions.load('ticino_warmup')
-- (1) Every COLLADA shape of the tiles (warmup_shapes.json, region.py) is loaded once as a TSStatic and deleted, so the
--     game writes its .cdae cache now: unwarmed, each new zone stuttered for ~30 s (0.1 s a shape, up to 46 s).
--     Never from the main menu: there the importer writes grey stub main.materials.json next to the shapes in the
--     user folder (the level's materials are not loaded).
-- (2) One small double-sided quad per sign/fuel material (warmup_materials.json) in front of the camera for
--     TEX_FRAMES frames, so the game cooks their textures (412 sign PNGs, 0.05-0.14 s each, ~4 s in all).
-- Tried on michi's PC (2026-10-28): 10,212 shapes in 968 s, 0 errors; 424 materials in ~4 s.
-- Progress: the log and <user folder>/ticino_warmup/progress.txt. Unloads itself when done.
local M = {}

M.BUDGET_MS = 250
M.TEX_FRAMES = 240
M.PROGRESS = '/ticino_warmup/progress.txt'

local S

local function clock() return os.clock() * 1000 end

local function progress(state)
  local line = string.format('%s shapes %d/%d loaded=%d failed=%d textures=%s elapsed=%.0fs', state, S.pos - 1,
    #S.shapes, S.done, S.failed, tostring(S.texState), (clock() - S.t0) / 1000)
  pcall(writeFile, M.PROGRESS, line .. '\n')
  return line
end

local function cached(p)
  return FS:fileExists('/temp' .. p:gsub('%.[dD][aA][eE]$', '.cdae'))
end

local function readList(name)
  local ok, v = pcall(jsonReadFile, '/levels/ticino/' .. name)
  return (ok and type(v) == 'table') and v or {}
end

local function texStart()
  local mats = S.mats
  local p, fwd = core_camera.getPosition(), core_camera.getForward()
  fwd = vec3(fwd.x, fwd.y, fwd.z):normalized()
  local right = fwd:cross(vec3(0, 0, 1)):normalized()
  local up = right:cross(fwd):normalized()
  local cols, step, s = 30, 0.25, 0.11
  local rows = math.ceil(#mats / cols)
  S.quads, S.texFrames, S.texFailed = {}, 0, 0
  for k, name in ipairs(mats) do
    local c, r = (k - 1) % cols, math.floor((k - 1) / cols)
    local centre = p + fwd * 8 + right * ((c - cols / 2) * step) + up * ((r - rows / 2) * step)
    local corners = { right * (-s) + up * (-s), right * s + up * (-s), right * s + up * s, right * (-s) + up * s }
    local verts, fv = {}, {}
    for i, v in ipairs(corners) do
      verts[i] = { x = v.x, y = v.y, z = v.z }
      fv[i] = { v = i - 1, n = 0, u = i - 1 }
    end
    local ok = pcall(function()
      local o = createObject('ProceduralMesh')
      o:registerObject('ticino_warm_' .. k)
      o.canSave = false
      o:createMesh({ { { verts = verts, normals = { { x = -fwd.x, y = -fwd.y, z = -fwd.z } },
        uvs = { { u = 0, v = 1 }, { u = 1, v = 1 }, { u = 1, v = 0 }, { u = 0, v = 0 } },
        faces = { fv[1], fv[2], fv[3], fv[1], fv[3], fv[4], fv[1], fv[3], fv[2], fv[1], fv[4], fv[3] },
        material = name } } })
      o:setPosition(centre)
      S.quads[#S.quads + 1] = o:getID()
    end)
    if not ok then S.texFailed = S.texFailed + 1 end
  end
  S.texState = string.format('%d quads (%d failed)', #S.quads, S.texFailed)
end

local function texEnd()
  for _, id in ipairs(S.quads) do
    local o = scenetree.findObjectById(id)
    if o then o:delete() end
  end
  S.texState = 'done ' .. #S.quads
end

local function onUpdate()
  if not S then return end
  if S.pos <= #S.shapes then
    local s = clock()
    while S.pos <= #S.shapes and clock() - s < M.BUDGET_MS do
      local p = S.shapes[S.pos]
      S.pos = S.pos + 1
      if not cached(p) then
        local ok = pcall(function()
          local o = createObject('TSStatic')
          o:setField('shapeName', 0, p)
          o:setField('collisionType', 0, 'None')
          o.canSave = false
          o:registerObject('')
          o:delete()
        end)
        if ok and cached(p) then S.done = S.done + 1 else S.failed = S.failed + 1 end
      end
    end
    if S.pos % 200 < 3 then progress('RUN') end
    return
  end
  if not S.quads then texStart(); progress('RUN'); return end
  S.texFrames = S.texFrames + 1
  if S.texFrames < M.TEX_FRAMES then return end
  texEnd()
  log('I', 'ticino', 'warm-up: ' .. progress('DONE'))
  S = nil
  extensions.unload('ticino_warmup')
end

local function onExtensionLoaded()
  local lvl = getCurrentLevelIdentifier and getCurrentLevelIdentifier()
  if lvl ~= 'ticino' then
    log('E', 'ticino', 'warm-up: load the level ticino first (the shapes need its materials), now: ' .. tostring(lvl))
    return false
  end
  S = { shapes = readList('warmup_shapes.json'), mats = readList('warmup_materials.json'), pos = 1, done = 0,
        failed = 0, t0 = clock(), texState = 'waiting' }
  log('I', 'ticino', string.format('warm-up: %d shapes, %d materials', #S.shapes, #S.mats))
  progress('START')
end

M.onUpdate = onUpdate
M.onExtensionLoaded = onExtensionLoaded
return M
