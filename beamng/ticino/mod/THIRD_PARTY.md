# Third-party code in the Ticino streaming mod

The terrain swap (terrainFile + postApply with a new file each time), the base colour fields, flushGroundCoverGrids after a
block change, runtime TSStatic objects with setPosRot and the game pause during a jump in lua/ge/extensions/ticino/
follow the code and the in-game measurements of BeamNG.Earth (https://github.com/TecnaGamer/BeamNG.Earth),
under the MIT licence. lua/ge/extensions/ticino/pace.lua follows its governor.lua (scene-changing frames isolated between calm ones), framepacer.lua (even frame pacing) and core.lua's hitch record (the engine's metrics of a slow frame); helper/ticino_helper.py's write_atomic follows its server/staging.py (temporary files outside the user folder, one read of each new file on Windows before the game opens it). The Ticino map on the M key (lua/ge/extensions/ticino/worldmap.lua, ui/ui-vue/mods/ticino/) follows its settings.lua redirectBigMap / toggleMap and its ui/ui-vue/mods/beamngEarth/index.js and EarthMap.vue (a full-screen UI route in place of the stock big map, tiles as level files):

```
MIT License

Copyright (c) 2026 TecnaGamer

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
