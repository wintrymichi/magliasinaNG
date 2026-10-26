-- Run by the game's mod manager once the mod is mounted: load the Ticino streaming extension and keep it loaded across
-- levels ('manual'). It does nothing outside the level 'ticino'.
extensions.load('ticino_stream')
setExtensionUnloadMode('ticino_stream', 'manual')
