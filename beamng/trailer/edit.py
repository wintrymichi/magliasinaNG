"""Cut the trailer: the frames of magliaso_trailer.lua, the Street View frames of sv_frames.py, the titles
and the music, timed on the bars of beats.py, into one MP4.
    python edit.py <edl.json> <frames dir> <sv dir> <music> <beats.json> <out.mp4> [--draft]
edl.json (beamng/trailer/edl.json): the clips in order, each with
  t          its start in the music (s), moved to the closest bar (or beat: "snap": "beat")
  shot       the shot of shots.py (its frames dir), "in" = seconds into the shot after its handle, "speed"
  compare    instead of shot: a `still` shot shown against its Street View frame (a wipe, then both)
  black      instead of shot: black (title cards on black)
  trans      how it starts: cut | dissolve | fadeblack (with "tdur" s)
  title      text over the clip: {"text", "sub", "at": s into the clip, "dur", "pos": centre|lower|upper|bottom}
             ("titles": a list of them, one after the other)
and at the top: "start" (where the music starts, s), "end" (the last bar), "fade_out" (s).
Clips are drawn at 2560 x 1440, 60 fps; --draft makes a quick 960 x 540 check.
The grade is a soft filmic look (lifted blacks, warm highlights, cooler shadows, a light vignette and grain).
"""
import bisect, csv, json, math, os, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FPS = 60
W, H = 2560, 1440
GRADE = ("eq=contrast=1.05:saturation=1.07:gamma=0.98,"
         "colorbalance=rs=-0.02:gs=0.0:bs=0.035:rh=0.035:gh=0.01:bh=-0.03,"
         "curves=all='0/0.03 0.5/0.5 1/0.97',vignette=angle=PI/5:mode=forward,noise=alls=3:allf=t")
FONT_DIRS = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"), "/usr/share/fonts"]


def font(size, weight="Light"):
    for d in FONT_DIRS:
        for root, _, files in os.walk(d):
            for want in (f"Montserrat-{weight}.ttf", f"Inter-{weight}.ttf", "DejaVuSans-ExtraLight.ttf", "DejaVuSans.ttf"):
                if want in files:
                    return ImageFont.truetype(os.path.join(root, want), size)
    return ImageFont.load_default()


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr[-3000:])
        raise SystemExit("ffmpeg failed: " + " ".join(cmd[:6]))


def snap(t, grid, tol=0.6):
    if not grid:
        return t
    i = bisect.bisect_left(grid, t)
    best = min((g for g in grid[max(0, i - 1):i + 1]), key=lambda g: abs(g - t))
    return best if abs(best - t) <= tol else t


# ---------------------------------------------------------------- frames
def shot_frames(frames_dir, shot):
    """[(t, path)] of a shot's saved frames, by time."""
    d = os.path.join(frames_dir, shot)
    rows = list(csv.DictReader(open(os.path.join(d, "frames.csv"))))
    return sorted((float(r["t"]), os.path.join(d, r["file"])) for r in rows)


def pick(frames, t):
    ts = [f[0] for f in frames]
    i = bisect.bisect_left(ts, t)
    cand = [j for j in (i - 1, i) if 0 <= j < len(frames)]
    return frames[min(cand, key=lambda j: abs(ts[j] - t))][1]


def title_png(title, w, h, path):
    """The text of a title card: thin capitals with wide spacing, a soft shadow."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = h / 1440
    f1, f2 = font(int(64 * s), "Light"), font(int(30 * s), "Regular")
    lines = [(title.get("text", "").upper(), f1, int(14 * s)), (title.get("sub", ""), f2, int(3 * s))]
    lines = [l for l in lines if l[0]]

    def spaced_w(txt, f, sp):
        return sum(d.textlength(c, font=f) for c in txt) + sp * max(0, len(txt) - 1)
    heights = [f.getbbox("Ag")[3] for _, f, _ in lines]
    total = sum(heights) + int(22 * s) * (len(lines) - 1)
    y = {"centre": (h - total) // 2, "lower": int(h * 0.74), "upper": int(h * 0.12),
         "bottom": int(h * 0.92) - total}[title.get("pos", "centre")]
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ds = ImageDraw.Draw(shadow)
    for (txt, f, sp), lh in zip(lines, heights):
        x = (w - spaced_w(txt, f, sp)) / 2
        for c in txt:
            ds.text((x + 2 * s, y + 2 * s), c, font=f, fill=(0, 0, 0, 210))
            d.text((x, y), c, font=f, fill=(255, 255, 255, 235))
            x += d.textlength(c, font=f) + sp
        y += lh + int(22 * s)
    out = Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6 * s)), img)
    out.save(path)


def cover(im, w, h):
    """Scaled to fill w x h without stretching, the overflow cropped evenly (a game window short of 16:9)."""
    k = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def compare_frames(game, sv, n, w, h, outdir, label_sv, label_game):
    """Street View on the left, the game on the right: a wipe from the right in the first second, a thin
    divider, a label on each side."""
    A = cover(Image.open(sv).convert("RGB"), w, h)
    B = cover(Image.open(game).convert("RGB"), w, h)
    s = h / 1440
    f = font(int(26 * s), "Regular")
    for i in range(n):
        t = i / FPS
        k = min(1.0, t / 1.2)
        k = k * k * (3 - 2 * k)
        split = int(w - (w / 2) * k)                    # the divider moves from the right edge to the middle
        frame = B.copy()
        frame.paste(A.crop((0, 0, split, h)), (0, 0))
        d = ImageDraw.Draw(frame)
        d.rectangle([split - max(1, int(2 * s)), 0, split + max(1, int(2 * s)), h], fill=(255, 255, 255))
        a = int(255 * min(1.0, max(0.0, (t - 1.0) / 0.5)))
        if a:
            lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            dl = ImageDraw.Draw(lay)
            pad = int(40 * s)
            dl.text((pad, h - pad - int(30 * s)), label_sv, font=f, fill=(255, 255, 255, a))
            tw = dl.textlength(label_game, font=f)
            dl.text((w - pad - tw, h - pad - int(30 * s)), label_game, font=f, fill=(255, 255, 255, a))
            frame = Image.alpha_composite(frame.convert("RGBA"), lay).convert("RGB")
        frame.save(os.path.join(outdir, "%05d.png" % i))


def render_clip(c, k, args, tmp, w, h):
    """One clip of the EDL, graded, with its title, to tmp/clip_k.mp4 (dur + transition overlaps)."""
    n = int(math.ceil(c["_len"] * FPS)) + 3          # a few spare frames at the tail: the next transition drops them
    seq = os.path.join(tmp, "seq%03d" % k)
    os.makedirs(seq, exist_ok=True)
    if "shot" in c:
        fr = shot_frames(args["frames"], c["shot"])
        t0 = fr[0][0]
        handle = c.get("handle", 1.5)
        start = t0 + handle + c.get("in", 0.0) - c["_pre"] * c.get("speed", 1.0)
        for i in range(n):
            os.symlink(os.path.abspath(pick(fr, start + i / FPS * c.get("speed", 1.0))), os.path.join(seq, "%05d.png" % i))
    elif "compare" in c:
        fr = shot_frames(args["frames"], c["compare"])
        meta = json.load(open(os.path.join(args["sv"], "sv_frames.json")))
        date = (meta.get(c["compare"], {}).get("date") or "")[:4]
        compare_frames(fr[len(fr) // 2][1], os.path.join(args["sv"], c["compare"] + ".png"), n, w, h, seq,
                       "STREET VIEW %s  ·  © Google" % date, "IN GAME  ·  MAGLIASINANG V3.1")
    else:                                               # black
        Image.new("RGB", (w, h)).save(os.path.join(seq, "black.png"))
        for i in range(n):
            os.symlink(os.path.join(seq, "black.png"), os.path.join(seq, "%05d.png" % i))
    vf = [f"scale={w}:{h}:flags=lanczos:force_original_aspect_ratio=increase,crop={w}:{h}"]
    if "compare" not in c and "black" not in c:
        vf.append(GRADE)
    inputs = ["-framerate", str(FPS), "-i", os.path.join(seq, "%05d.png")]
    fc = "[0:v]" + ",".join(vf) + "[v]"
    titles = c.get("titles") or ([c["title"]] if c.get("title") else [])
    for j, ti in enumerate(titles):                     # one or more texts over the clip, each fading in and out
        tp = os.path.join(tmp, "title%03d_%d.png" % (k, j))
        title_png(ti, w, h, tp)
        at = c["_pre"] + ti.get("at", 0.5)
        dur = ti.get("dur", max(1.0, c["_dur"] - ti.get("at", 0.5) - 0.5))
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", str(c["_len"]), "-i", tp]
        fc += (f";[{j + 1}:v]format=rgba,fade=t=in:st={at:.3f}:d=0.8:alpha=1,"
               f"fade=t=out:st={at + dur - 0.8:.3f}:d=0.8:alpha=1[t{j}];[v][t{j}]overlay=0:0[v]")
    out = os.path.join(tmp, "clip%03d.mp4" % k)
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc, "-map", "[v]", "-frames:v", str(n),
         "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", out])
    return out


def plan(edl, beats):
    """Clip times are trailer times; the beat grid is in music time, shifted by the music's start."""
    st = edl.get("start", 0.0)
    grid_bar = [b - st for b in beats.get("downbeats", []) if b >= st]
    grid_beat = [b - st for b in beats.get("beats", []) if b >= st]
    clips = edl["clips"]
    for c in clips:
        c["_t"] = snap(c["t"], grid_beat if c.get("snap") == "beat" else grid_bar)
    end = snap(edl["end"], grid_bar)
    for i, c in enumerate(clips):
        nxt = clips[i + 1]["_t"] if i + 1 < len(clips) else end
        c["_dur"] = nxt - c["_t"]
        tin = c.get("tdur", 0.6) if c.get("trans", "cut") != "cut" else 0.0
        tout = clips[i + 1].get("tdur", 0.6) if i + 1 < len(clips) and clips[i + 1].get("trans", "cut") != "cut" else 0.0
        c["_pre"], c["_post"] = tin / 2, tout / 2
        c["_len"] = c["_dur"] + c["_pre"] + c["_post"]
    return clips, end


def main():
    a = sys.argv[1:]
    draft = "--draft" in a
    a = [x for x in a if x != "--draft"]
    edl_p, frames, sv, music, beats_p, out = a
    w, h = (960, 540) if draft else (W, H)
    edl = json.load(open(edl_p))
    beats = json.load(open(beats_p))
    clips, end = plan(edl, beats)
    t_first = clips[0]["_t"]
    tmp = tempfile.mkdtemp(prefix="trailer_")
    try:
        files = []
        for k, c in enumerate(clips):
            files.append(render_clip(c, k, {"frames": frames, "sv": sv}, tmp, w, h))
            print("clip %2d %-28s %6.2f s at %6.2f" % (k, c.get("shot") or c.get("compare") or "black", c["_dur"], c["_t"]), flush=True)
        # the transitions: xfade on every boundary (a cut is a one-frame fade)
        inputs, fc, last, off = [], [], "[0:v]", 0.0
        for f in files:
            inputs += ["-i", f]
        for i in range(1, len(clips)):
            c = clips[i]
            kind = c.get("trans", "cut")
            d = c.get("tdur", 0.6) if kind != "cut" else 1.0 / FPS
            boundary = c["_t"] - t_first
            off = boundary - (d / 2 if kind != "cut" else d)
            tr = {"cut": "fade", "dissolve": "fade", "fadeblack": "fadeblack"}[kind]
            fc.append(f"{last}[{i}:v]xfade=transition={tr}:duration={d:.4f}:offset={off:.4f}[x{i}]")
            last = f"[x{i}]"
        total = end - t_first
        start = edl.get("start", 0.0) + t_first
        fade = edl.get("fade_out", 3.0)
        audio = (f"[{len(files)}:a]atrim=start={start:.3f}:duration={total:.3f},asetpts=PTS-STARTPTS,"
                 f"afade=t=in:d=1.5,afade=t=out:st={total - fade:.3f}:d={fade:.3f},loudnorm=I=-14:TP=-1.5,aresample=48000[a]")
        fc.append(audio)
        vlast = last if len(files) > 1 else "[0:v]"
        fc.append(f"{vlast}fade=t=in:d=1.0,fade=t=out:st={total - 1.5:.3f}:d=1.5[vout]")
        run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-i", music, "-filter_complex", ";".join(fc),
             "-map", "[vout]", "-map", "[a]", "-t", f"{total:.3f}", "-r", str(FPS),
             "-c:v", "libx264", "-preset", "slow" if not draft else "veryfast", "-crf", "16" if not draft else "23",
             "-maxrate", "30M", "-bufsize", "45M",          # 90 s stays under 400 MB
             "-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             "-c:a", "aac", "-b:a", "320k", out])
        print(out, "%.1f s" % total)
    finally:
        if not os.environ.get("TRAILER_KEEP_TMP"):
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print("kept", tmp)


if __name__ == "__main__":
    main()
