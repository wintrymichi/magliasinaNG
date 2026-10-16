"""Beats, bars and loudness of the trailer's music, for the cuts of edit.py.
    python beats.py <music.mp3> [out.json]          (default: beats.json next to the music)
Writes: duration, tempo, beats (s), downbeats (s, the first beat of each 4/4 bar, phase chosen where
the onsets are strongest), and the loudness per half second (RMS in dB) to see the build-up and the
climax. Needs librosa.
"""
import json, os, sys
import numpy as np


def analyse(path):
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True)
    dur = len(y) / sr
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, units="frames", tightness=120)
    beats = librosa.frames_to_time(frames, sr=sr)
    strength = onset[np.clip(frames, 0, len(onset) - 1)]
    phase = int(np.argmax([strength[k::4].mean() if len(strength[k::4]) else 0 for k in range(4)]))
    downbeats = beats[phase::4]
    hop = int(sr * 0.5)
    rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-5))
    return {"file": os.path.basename(path), "duration": round(dur, 3), "tempo": round(float(np.atleast_1d(tempo)[0]), 2),
            "beats": [round(float(b), 3) for b in beats], "downbeats": [round(float(b), 3) for b in downbeats],
            "loudness_db_per_0.5s": [round(float(v), 1) for v in db]}


def main():
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(src)), "beats.json")
    r = analyse(src)
    json.dump(r, open(out, "w"), indent=1)
    bar = np.diff(r["downbeats"]).mean() if len(r["downbeats"]) > 1 else 0
    print("%s: %.1f s, %.1f bpm, %d beats, %d bars (%.2f s each) -> %s" % (
        r["file"], r["duration"], r["tempo"], len(r["beats"]), len(r["downbeats"]), bar, out))
    # a coarse loudness curve, 5 s per character, to see where the music builds
    db = np.array(r["loudness_db_per_0.5s"])
    marks = " .:-=+*#%@"
    lo, hi = np.percentile(db, 5), db.max()
    curve = "".join(marks[int(np.clip((db[i:i + 10].mean() - lo) / max(hi - lo, 1e-6), 0, 0.999) * len(marks))]
                    for i in range(0, len(db), 10))
    print("loudness (5 s per mark):", curve)


if __name__ == "__main__":
    main()
