-- Run by the game's mod manager once the mod is mounted: keep the Ticino streaming extension loaded across levels
-- ('manual': the mod manager loads it right after the modScripts). It does nothing outside the level 'ticino'.
setExtensionUnloadMode('ticino_stream', 'manual')
