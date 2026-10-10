# magliaso_pura v2.8 – in-game test, michi's PC (2026-10-11, BeamNG.drive 0.39.4, Linux native, RTX 4070, 14 GB RAM)

Zip: final-build-test.zip (sha256 2f5450f3…d310 OK) -> magliaso_pura_v2.8.zip 513,780,296 B, md5 b7090f434dfa2147c591e3ff999c59eb (package.log digest d3480aa7…700d).

## Run
- Load: 130.5 s from launch to world ready (cold, temp/levels cache cleared). RSS at ready 5.27 GB, peak RSS 6.43 GB, lowest MemAvailable 2.3 GB. No crash; 40.5 min total, game exited by itself.
- First launch failed with "map not found": mods/db.json had magliaso_pura_v2.8 "active": false (already before the swap). Set to true (original in old_mods/db.json.bak).
- AI drives (ai.driveUsingPath on the AI road network, rally car, limit 14 m/s):
  - Magliaso -> Pura (cantonale, 3.68 km): reached the end, 498 s. 5 real stops: start (AI did not start, no damage), Pura nucleo [89,-813] crash (check_level "ostacolo sulla strada" object at [87.5,-810.4], 3.5 m), [58,-748] crash, [27,-677] crash (building obstacle listed at [44,-651]), end [-733,1079] in Pura (Via Mulino) crash.
  - Arosio -> Mugena -> Vezio -> Breno -> Miglieglia -> Novaggio (9.61 km, one connected road): reached the end, 926 s. 3 real stops with damage: [1395,6440] Mugena (check_level "strada staccata dal terreno" 34 m), [917,6049] Vezio (drive_test HARD 13.0 / TWIST 9.7 at "Pasquée da Vésc" 22 m; "strada sotto il terreno" 32 m), [-1238,4231] Via Cantonale near Miglieglia (check_level "ostacolo sulla strada", ponte o gradino, 1.8 m).
  - All other resets ("below ground") were false positives of the test's ground probe (car on route at normal speed).

## Items
1. Terrain behind retaining walls: mostly OK, no large pale flat terrain triangles at the cantonale hairpin, Agno or Ponte Tresa. Still visible: pale/white jagged sawtooth bands on top of stone walls (wall caps), e.g. w1_tornante_cantonale_060, w1_tornante_cantonale_b_045, g1_guardrail_along_b, Arosio drive shot 19; pale grey slabs on the Magliasina bridge abutments (b_ponte_magliaso_2/5). Pale irregular terrain patches in the grass at Agno (w2_agno_lago_090).
2. Guard rails: OK at 6 sites (cantonale hairpin, Agno, Pura, Arosio pass, Caslano, Cademario): full rail + posts, no doubled rails seen.
3. Signs: OK at 8 roundabout give-way signs (one triangle + roundabout plate per post, no doubles). The one double from doubles.json is visible at [-30,-416]: two keep-right signs on the same island, about 4 m apart, both facing the same way.
4. Road Arosio–Miglieglia–Novaggio: exists, connected, AI drove all of it; 3 bumps/obstacles stopped the AI (see above).
5. Magliaso bridge near the roundabout: underside textured (stone), not blocky. The low views are partly under the river surface.
6. Shots: 106 in shots/all (1600 px JPG), 15 picks in shots/best.
