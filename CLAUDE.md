# Notes for Claude sessions on MagliasinaNG

Mistakes made in earlier sessions and what to do instead. Add to this list when a new one costs time.

## Building the level locally

- Mirror `.github/workflows/v3_build_test.yml` with `MAGLIASO_ROOT` etc. exported. Without the env vars,
  `config.py` falls back to Windows paths (`BEAMNG_USER = C:\Users\...`) and scripts silently find nothing
  (a mesh search returned no items until the build env was sourced).
- A full build takes about 3.5 h; `build_level.py --finish <steps>` reruns single finish steps. After a
  container restart mid-build, resume from the failed step instead of starting over.
- Never run whole-terrain analysis (full 8192x8192 arrays, the 0.5 m DTM) while a build runs: it OOM-killed
  a pool worker and deadlocked the `optimize` step. Use small windows (memmap slices) during a build.
- `pkill -f build_level.py` also matches the shell running the pkill and kills it. Use `pkill -f "[b]uild_level.py"`.
- The build rewrites files in `beamng/dati` (e.g. `ponti.json`). Run `git checkout -- beamng/dati` before
  committing, or generated data ends up in the commit.
- The cloud container idles when no turn is active: keep a foreground wait loop while a build runs
  (`timeout 590 bash -c 'until grep -qE "BUILD DONE|Traceback" LOG; do sleep 20; done'`).
- Push work often. An earlier session lost the fuel stations module because it was never pushed.

## Terrain fixes

- Terrain heights are written in several places, in this order: the road carve override (`terrain_override`,
  applied as the height under and one terrain step around every paved mesh), the posts (walls.carve_terrain +
  adjust_terrain_roadside, water.lake_bed, rivers, railway.carve_terrain), then `min(H, override)`, then the
  finish steps `unpaved` and `paved_edges` (network_mesh.block raises ground up to EMB_MAX). Fixing one of
  them repeatedly let the same teeth come back from another.
- To find which step made a spike, compare in a small window: the final `.ter` (uint16 at offset 5,
  Z0/MAXH from the terrain json), `work/terrain_heights.npy` (stage terrain), the DTM, and the override
  stored in `work/roads_state.npz` (`ov_i`, `ov_v`). Only then change code.
- The override raises terrain, not only lowers it: a pavement on top of a retaining wall raised the vertices
  one ring beyond the wall carve to pavement height (single white teeth beside the railway under Magliaso,
  about 2500 over the map). walls.carve_terrain now lowers that ring on the low side of a wall.
- Do not tell the side of a wall from a vertex's own height: the DTM smears walls into slopes. Read the
  ground a few metres out on both sides (walls.wall_side), and read beyond any vertex that may itself be raised.
- Anything that raises ground near the railway must respect its bed (railway.bed_fn, network_mesh rail caps).

## Meshes

- Check winding/orientation when placing text or UVs along an outline: the fuel station fascia text was
  mirrored on outlines that ran the other way.

## Working with cat (the owner)

- Show the 3D renders and wait for cat's OK before running the GitHub Actions rebuild workflow. No PRs
  or merges without asking.
- Keep the README "Known limitations" up to date when one gets fixed.
- Reply in Italian, times in CEST, few subagents.
