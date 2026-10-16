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
python shots.py --scout                     # 1. check the framing
BeamNG.drive.x64 -level magliaso_pura -onLevelLoad_ext magliaso_trailer
python shots.py                             # 2. the full shots, same launch
python sv_frames.py sv/
python beats.py GoldenHour.mp3
python edit.py edl.json <user>/screenshots/magliaso_trailer sv/ GoldenHour.mp3 beats.json trailer_draft.mp4 --draft
python edit.py edl.json <user>/screenshots/magliaso_trailer sv/ GoldenHour.mp3 beats.json trailer_v3.mp4
```

Music: "Golden Hour" by Scott Buckley, CC BY 4.0 (credit in the video and its description). Street View imagery © Google, credited on screen. The panoramas are a visual reference for the video only; they never enter the level or the repository.
