-- Ticino: the level's shared object textures cooked at the start, before any streamed object binds them.
-- PC 2026-11-01 (server mode, cold cache): house walls kept the "IMPORTING TEXTURE" placeholder for 10 minutes. The log
-- had t_bld_plaster_b / t_bld_ashlar_b cooked without error, but no "reloadResource File changed" for them (it came
-- for plaster_nm and ashlar_ao): a material bound while its colour map was still being cooked kept the placeholder.
-- So every material of the level's own art (not the per-sign/prop plates, not the terrain) gets one small quad in front
-- of the camera for FRAMES frames as the level starts (warmup.lua's way), before the streamer makes objects.
local M = {}

M.FRAMES = 120            -- frames the quads stay (the cook of ~100 materials took ~40 s once on the PC, cold)
M.SKIP = { '/art/shapes/props/', '/art/shapes/signs/', '/art/terrains/' }
M.MAX = 400

local S

local function skip(p)
  for _, s in ipairs(M.SKIP) do if p:find(s, 1, true) then return true end end
  return false
end

-- the names of the level's materials with a PNG map
function M.list(level)
  local out, files = {}, {}
  pcall(function() files = FS:findFiles('/levels/' .. level .. '/art/', '*.materials.json', -1, true, false) or {} end)
  for _, f in ipairs(files) do
    if not skip(f) then
      local ok, d = pcall(jsonReadFile, f)
      if ok and type(d) == 'table' then
        for name, m in pairs(d) do
          if type(m) == 'table' and m.class == 'Material' then
            local png = false
            for _, st in ipairs(type(m.Stages) == 'table' and m.Stages or {}) do
              for _, v in pairs(st) do
                if type(v) == 'string' and v:lower():sub(-4) == '.png' then png = true end
              end
            end
            if png and #out < M.MAX then out[#out + 1] = name end
          end
        end
      end
    end
  end
  table.sort(out)
  return out
end

local function place()
  local p, fwd = core_camera.getPosition(), core_camera.getForward()
  fwd = vec3(fwd.x, fwd.y, fwd.z):normalized()
  local right = fwd:cross(vec3(0, 0, 1)):normalized()
  local up = right:cross(fwd):normalized()
  local cols, step = 20, 0.25
  local rows = math.ceil(#S.ids / cols)
  for k, id in ipairs(S.ids) do
    local o = scenetree.findObjectById(id)
    if o then
      local c, r = (k - 1) % cols, math.floor((k - 1) / cols)
      o:setPosition(p + fwd * 6 + right * ((c - cols / 2) * step) + up * ((r - rows / 2) * step))
    end
  end
end

function M.start(level)
  M.clear()
  local mats = M.list(level)
  S = { ids = {}, frames = 0, failed = 0, n = #mats }
  local s = 0.1
  for k, name in ipairs(mats) do
    local ok = pcall(function()
      local o = createObject('ProceduralMesh')
      o:registerObject('ticino_texwarm_' .. k)
      o.canSave = false
      local v = { { x = -s, y = 0, z = -s }, { x = s, y = 0, z = -s }, { x = s, y = 0, z = s }, { x = -s, y = 0, z = s } }
      local fv = {}
      for i = 1, 4 do fv[i] = { v = i - 1, n = 0, u = i - 1 } end
      o:createMesh({ { { verts = v, normals = { { x = 0, y = -1, z = 0 } },
        uvs = { { u = 0, v = 1 }, { u = 1, v = 1 }, { u = 1, v = 0 }, { u = 0, v = 0 } },
        faces = { fv[1], fv[2], fv[3], fv[1], fv[3], fv[4], fv[1], fv[3], fv[2], fv[1], fv[4], fv[3] },
        material = name } } })
      S.ids[#S.ids + 1] = o:getID()
    end)
    if not ok then S.failed = S.failed + 1 end
  end
  log('I', 'ticino', string.format('texture warm-up: %d materials of the level art, %d quads (%d failed)', #mats,
    #S.ids, S.failed))
  if #S.ids == 0 then S = nil end
end

-- each frame while it runs (true: still running)
function M.step()
  if not S then return false end
  pcall(place)
  S.frames = S.frames + 1
  if S.frames < M.FRAMES then return true end
  log('I', 'ticino', string.format('texture warm-up done: %d quads for %d frames', #S.ids, S.frames))
  M.clear()
  return false
end

function M.clear()
  if not S then return end
  for _, id in ipairs(S.ids) do
    local o = scenetree.findObjectById(id)
    if o then o:delete() end
  end
  S = nil
end

function M.running() return S ~= nil end

return M
