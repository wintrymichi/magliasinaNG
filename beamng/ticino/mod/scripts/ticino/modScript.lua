-- Run by the game's mod manager once the mod is mounted: load the Ticino streaming extension and keep it loaded across
-- levels ('manual'). It does nothing outside the level 'ticino'.
setExtensionUnloadMode('ticino_stream', 'manual')    -- before the load: the game warned when it came after (laptop run 1)
extensions.load('ticino_stream')
-- the Ticino map on M (worldmap.lua): only in the level ticino
setExtensionUnloadMode('ticino_worldmap', 'manual')
extensions.load('ticino_worldmap')
