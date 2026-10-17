# v3 trailer tools

The trailer of v3 is rendered inside the game, frame by frame, and cut on the bars of the music.

| File | What it does |
|---|---|
| `shots.py` | The shot list (drone moves, walks at eye height, Street View stills, AI-car cinematics, gameplay) → `<user>/magliaso_trailer_shots.json`. `--scout`: three stills per shot to check the framing first. |
| `../pipeline/bng_lua/magliaso_trailer.lua` | The game extension that renders the shots: every frame saved as PNG with its time (camera moves on a virtual clock, cars in slow motion, paused while a frame is saved). Temporary: remove it from the game folders after the capture. |
| `sv_frames.py` | The Street View panorama of each comparison, reprojected to the game camera's place, direction and field of view. |
| `beats.py` | Beats, bars and loudness of the music (librosa). |
| `edl.json` | The cut: clips in music time, transitions, titles. |
| `edit.py` | Builds the MP4: picks the frames at 60 fps, grades, titles, Street View wipes, transitions, music (loudness −14 LUFS). |

```
# the extension: <user>/lua/ge/extensions/magliaso/trailer.lua; fonts: Montserrat-Light/Regular.ttf in fonts/ (not in git)
python shots.py --scout [--todtest]         # 1. check the framing (and the level's clock at the first and last shot)
BeamNG.drive.x64 -level magliaso_pura -onLevelLoad_ext magliaso_trailer
python shots.py                             # 2. the full shots, same launch
python sv_frames.py sv/
python beats.py GoldenHour.mp3
python edit.py edl.json <user>/screenshots/magliaso_trailer sv/ GoldenHour.mp3 beats.json trailer_draft.mp4 --draft
python edit.py edl.json <user>/screenshots/magliaso_trailer sv/ GoldenHour.mp3 beats.json trailer_v3.mp4
```

Learned on the v3.1 shoot: `job.yield()` can resume inside the same frame (wait on rendered frames instead);
pausing and resuming the physics every frame locked the game up, and stepping it (`be:physicsStep`) upset the AI
driver, so cars run in continuous slow motion; the AI needs waypoints along the wanted road (`cantonale()` in
shots.py follows the Street View track), or it takes the shortest way through any alley. The level's clock:
0.79 pink dawn, 0.24 golden light, 0.256 the sun on the western ridge, 0.265 already after sunset.
On a real KDE desktop the borderless window loses the panel's height (frames 2560 x 1327) and asking the game for
fullscreen from the extension fails (320 x 240, or ignored): shoot in a virtual KWin session (`kwin_wayland --virtual
--xwayland --width 2560 --height 1440`). The v2 cut (1:55) starts the music 14 bars earlier, at 172.664 s.
v3.1 has no pump objects for its gas stations: `gameplay_markerInteraction` throws every frame while a car
drives, so the extension unloads it for the shoot.

Music: "Golden Hour" by Scott Buckley, CC BY 4.0 (credit in the video and its description). Street View imagery © Google, credited on screen. The panoramas are a visual reference for the video only; they never enter the level or the repository.
