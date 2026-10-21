"""Ambient sounds (v3.0.40), in the built level.

Up to v3.0 the map had no sound of its own: only the engine, the tyres and the game's wind. Here the build
places the game's own sounds (FMOD events of BeamNG.drive, nothing recorded or downloaded) as SFXEmitters in
MissionGroup/ambient_sounds, where a driver hears them:
- water: along the rivers (OpenStreetMap waterway=river: the Magliasina, the Tresa, the Vedeggio) one emitter
  every RIVER_STEP m, only within NEAR_ROAD m of an AI road; the streams (waterway=stream) where an AI road
  crosses them, at most one every STREAM_STEP m;
- the lake: on the shore of Lake Lugano (terrain at the WaterBlock's level, its largest water body), one every
  LAKE_STEP m within NEAR_ROAD m of a road;
- the woods: where the forest of the level is dense (at least WOOD_DENSITY trees per hectare, counted in
  WOOD_CELL m squares) and near a road, one emitter every WOOD_STEP m. BeamNG 0.40 has no birds, crickets or
  church bells (beamng/dati/ambient_events.json); its forest beds (Ambient>Roomtones>Roomtone_ConiferousDeciduous_*)
  may be 2D, heard everywhere at full volume, so the woods are silent unless the "use" entry of that file names
  an event after listening in the game ("forest": "...").

Which events exist: beamng/dati/ambient_events.json, the ambient events of the game read once from an install
(python ambient_sounds.py --scan <BeamNG.drive folder>: every `track` of an SFXEmitter in the vanilla levels,
content/levels/*.zip, and every event path in the FMOD strings banks), kept in the repository so that two builds
of a commit are the same with or without the game. For each sound the first of its candidates the game has, else
the first event matching its pattern (3D events only: a 2D event would be heard everywhere at full volume).
Without that file the first candidate and the report says "not checked": a sound whose event the game lacks is
silent, it breaks nothing. In 0.40 the strings bank keeps the paths as a prefix trie and --scan finds none of
them: the file of 0.40 was written by hand from the trie (its "_about").

A finishing step of build_level.py (FINISH); alone: python build_level.py --finish ambient_sounds
"""
import json, os, re, sys, time, zipfile
import numpy as np
import shapely
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
import bng
import osm
import network_mesh as pu
import walls as pw
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE
from markings_net import read_items

GROUP = "ambient_sounds"
NEAR_ROAD = 200.0          # m from an AI road at most: farther no driver hears it
RIVER_STEP = 150.0         # m between two emitters along a river
STREAM_STEP = 450.0        # m between two emitters on the streams (at the road crossings)
STREAM_MIN = 150.0         # m: a stream shorter than this makes no sound of its own
LAKE_STEP = 160.0          # m between two emitters on the shore
WOOD_CELL = 100.0          # m, the squares the trees are counted in
WOOD_DENSITY = 30.0        # trees per hectare at least: a wood
WOOD_STEP = 450.0          # m between two places in the woods
OVER = 1.0                 # m over the ground or the water: the emitters of water and woods
DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
EVENTS_PINNED = os.path.join(DATI, "ambient_events.json")

# (role, subgroup, candidates, pattern, volume): candidates in order of preference (BeamNG 0.40), pattern for any
# other 3D event of the game that fits (None: candidates only)
SOUNDS = [
    ("river", "ambient_water", ["event:>Ambient>Water>River"], r"river|torrent|rapids", 1.0),
    ("stream", "ambient_water", ["event:>Ambient>Water>River"], None, 0.45),     # the river, quieter
    ("lake", "ambient_water", ["event:>Ambient>Water>Waves"], r"lake|shore|lapping|waves?\b", 0.8),
    ("forest", "ambient_woods", [], None, 0.7),                                 # see the docstring
]


# ------------------------------------------------------------------ the game's events
def game_events(game):
    """(set of event paths 'event:>A>B', how many files they were read from) of the game install `game`."""
    ev, src = set(), {"levels": 0, "banks": 0}
    track = re.compile(rb'"track"\s*:\s*"(event:>[^"]{3,160})"')
    path = re.compile(rb"event:/[\x20-\x7e]{3,160}?(?=[\x00-\x1f]|$)")
    for dp, _, fs in os.walk(game):
        for f in fs:
            p = os.path.join(dp, f)
            try:
                if f.endswith(".strings.bank"):
                    ev |= {"event:>" + m.decode("ascii")[7:].replace("/", ">") for m in path.findall(open(p, "rb").read())}
                    src["banks"] += 1
                elif f.endswith(".zip") and os.sep + "levels" in dp:
                    with zipfile.ZipFile(p) as z:
                        for n in z.namelist():
                            if n.endswith(".level.json") or n.endswith(".strings.bank"):
                                b = z.read(n)
                                if n.endswith(".strings.bank"):
                                    ev |= {"event:>" + m.decode("ascii")[7:].replace("/", ">") for m in path.findall(b)}
                                    src["banks"] += 1
                                elif b"SFXEmitter" in b:
                                    ev |= {m.decode("utf-8") for m in track.findall(b)}
                                    src["levels"] += 1
            except (OSError, zipfile.BadZipFile, UnicodeDecodeError):
                continue
    return ev, src


def scan(game):
    """Reads the events of the game install and writes EVENTS_PINNED."""
    ev, src = game_events(game)
    ver = None
    for f in ("version.txt", "integrity.json"):
        p = os.path.join(game, f)
        if os.path.exists(p) and f.endswith(".txt"):
            ver = open(p, encoding="utf-8", errors="replace").read().strip()[:40]
    keep = sorted(e for e in ev if e.startswith("event:>Ambient") or e.startswith("event:>Environment"))
    use = pinned_events()[1]
    json.dump({"game": ver, "read_from": src, "events_total": len(ev), "events": keep,
               "picked": {r: e for r, (e, _) in pick_events(set(ev), use).items()}, "use": use},
              open(EVENTS_PINNED, "w", encoding="utf-8"), indent=1)
    print(EVENTS_PINNED, len(ev), "events,", len(keep), "ambient;", src)


def pinned_events():
    """(events of the game or None, {role: event chosen by hand}: the "use" entry of EVENTS_PINNED, after
    listening in the game; an empty string silences that sound)."""
    if not os.path.exists(EVENTS_PINNED):
        return None, {}
    d = json.load(open(EVENTS_PINNED, encoding="utf-8"))
    return (set(d["events"]) if d.get("events") else None), d.get("use", {})


def pick_events(events, use=None):
    """{role: (event or None, how)}: how 'chosen' (the "use" entry), 'game' (the game has a candidate),
    'pattern' (a matching event of the game), 'not checked' (no list of the game's events: the first candidate)."""
    out = {}
    for role, _, cand, pat, _ in SOUNDS:
        if use and role in use:
            out[role] = (use[role] or None, "chosen")
            continue
        if events is None:
            out[role] = (cand[0], "not checked") if cand else (None, "no candidate without the game")
            continue
        have = next((c for c in cand if c in events), None)
        if have:
            out[role] = (have, "game")
            continue
        if pat is None:
            out[role] = (None, "not in the game")
            continue
        rx = re.compile(pat, re.I)
        m = sorted(e for e in events if ">2D>" not in e and "Vehicle" not in e and rx.search(e.split(">", 2)[-1]))
        amb = [e for e in m if e.startswith("event:>Ambient")]
        out[role] = ((amb or m)[0], "pattern") if (amb or m) else (None, "not in the game")
    return out


# ------------------------------------------------------------------ places
def thin(P, step):
    """Indices of the points kept so that no two are closer than step (greedy, in the given order)."""
    if not len(P):
        return []
    tree, keep, taken = cKDTree(P), [], np.zeros(len(P), bool)
    for i in range(len(P)):
        if taken[i]:
            continue
        keep.append(i)
        taken[tree.query_ball_point(P[i], step)] = True
    return keep


def along(line, step):
    n = max(int(line.length // step), 0)
    d = (np.arange(n + 1) + 0.5) * (line.length / (n + 1))
    return np.array([[p.x, p.y] for p in line.interpolate(d)]).reshape(-1, 2)


def ai_roads(zi, lv):
    """Points every ~5 m along the AI roads (their axes)."""
    pts = []
    for road in read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json"):
        nd = np.asarray(road.get("nodes", []), np.float64)
        if len(nd) < 2:
            continue
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(nd[:, :2], axis=0).T))]
        sd = np.linspace(0, s[-1], max(int(s[-1] / 5), 1) + 1)
        pts.append(np.column_stack([np.interp(sd, s, nd[:, 0]), np.interp(sd, s, nd[:, 1])]))
    return np.concatenate(pts) if pts else np.zeros((0, 2))


def river_places(ways, roads):
    near = lambda P: P[roads.query(P)[0] <= NEAR_ROAD] if len(P) else P
    rivers = [w["line"] for w in ways if w["tags"].get("waterway") == "river"]
    P = np.concatenate([along(l, RIVER_STEP / 4) for l in rivers]) if rivers else np.zeros((0, 2))
    P = near(P)
    P = P[thin(P, RIVER_STEP)]
    streams = [w["line"] for w in ways if w["tags"].get("waterway") == "stream" and w["line"].length >= STREAM_MIN]
    S = np.concatenate([along(l, 4.0) for l in streams]) if streams else np.zeros((0, 2))
    S = S[roads.query(S)[0] <= 12.0] if len(S) else S          # where a road crosses or runs beside it
    if len(P) and len(S):
        S = S[cKDTree(P).query(S)[0] > RIVER_STEP / 2]          # the river is heard there already
    S = S[thin(S, STREAM_STEP)]
    return P, S


def lake_places(q, wl, roads, stride=8):
    """Points on the lake shore (on the water, OVER the shore line): the largest body of terrain under the
    water level, read every `stride` terrain vertices."""
    z = pu.Z0 + q[::stride, ::stride].astype(np.float64) / 65535.0 * pu.MAXH
    wet = z < wl - 0.05
    lab, n = ndi.label(wet)
    if not n:
        return np.zeros((0, 2))
    lake = lab == (np.argmax(np.bincount(lab.ravel())[1:]) + 1)
    shore = lake & ndi.binary_dilation(~lake)
    r, c = np.nonzero(shore)
    P = np.column_stack([TER_X0 + c * stride * TER_SQUARE, TER_Y0 + r * stride * TER_SQUARE])
    P = P[roads.query(P)[0] <= NEAR_ROAD]
    return P[thin(P, LAKE_STEP)]


def wood_places(zi, lv, roads):
    xy = []
    for n in zi.namelist():
        if n.startswith(f"{lv}/forest/") and n.endswith(".forest4.json") and "guardrail" not in n:
            for o in read_items(zi, n):
                if "pos" in o:
                    xy.append(o["pos"][:2])
    if not xy:
        return np.zeros((0, 2)), 0
    xy = np.asarray(xy, np.float64)
    k = np.floor(xy / WOOD_CELL).astype(np.int64)
    cells, cnt = np.unique(k, axis=0, return_counts=True)
    dense = cells[cnt >= WOOD_DENSITY * (WOOD_CELL / 100.0) ** 2]
    P = (dense + 0.5) * WOOD_CELL
    P = P[roads.query(P)[0] <= NEAR_ROAD * 0.6] if len(P) else P
    # nearer the roads first
    P = P[np.argsort(roads.query(P)[0])] if len(P) else P
    return P[thin(P, WOOD_STEP)], len(dense)


def emitter(name, pos, event, volume, parent):
    return {"class": "SFXEmitter", "name": name, "persistentId": bng.pid(), "__parent": parent,
            "position": [round(float(v), 2) for v in pos], "track": event, "fileName": "",
            "playOnAdd": True, "useTrackDescriptionOnly": False, "is3D": True, "isLooping": True,
            "volume": float(volume)}


# ------------------------------------------------------------------ the step
def ambient_sounds_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    events, use = pinned_events()
    ev = pick_events(events, use)
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    ground = lambda P: pu.terrain_top(q, P[:, 0].astype(float), P[:, 1].astype(float))
    wl = None
    for f in zi.namelist():
        if f.startswith(f"{lv}/main/") and f.endswith("items.level.json") and wl is None:
            for o in read_items(zi, f):
                if o.get("class") == "WaterBlock" and str(o.get("name", "")).startswith("LagoDiLugano"):
                    wl = float(o["position"][2])
                    break
    R = ai_roads(zi, lv)
    roads = cKDTree(R if len(R) else np.zeros((1, 2)) + 1e9)
    ways, _ = osm.load()
    river, stream = river_places(ways, roads)
    lake = lake_places(q, wl, roads) if wl is not None else np.zeros((0, 2))
    woods, n_dense = wood_places(zi, lv, roads)

    def z_of(P, up):
        return np.column_stack([P, ground(P) + up]) if len(P) else np.zeros((0, 3))

    places = {"river": z_of(river, OVER), "stream": z_of(stream, OVER),
              "lake": np.column_stack([lake, np.full(len(lake), (wl or 0) + OVER)]) if len(lake) else np.zeros((0, 3)),
              "forest": z_of(woods, OVER + 3.0)}
    objs, subgroups = [], {}
    rep = {"events": {r: {"event": e, "how": h} for r, (e, h) in ev.items()},
           "game_events": None if events is None else len(events),
           "emitters": {}, "silent": [], "dense_wood_cells": int(n_dense)}
    for role, sub, _, _, vol in SOUNDS:
        e = ev[role][0]
        P = places[role]
        if e is None:
            rep["silent"].append(role)
            rep["emitters"][role] = 0
            continue
        subgroups[sub] = True
        for i, p in enumerate(P):
            objs.append(emitter(f"amb_{role}_{i:03d}", p, e, vol, sub))
        rep["emitters"][role] = len(P)
    files = {}
    rows = [{"name": GROUP, "class": "SimGroup", "persistentId": bng.pid(), "__parent": "MissionGroup"}]
    rows += [{"name": s, "class": "SimGroup", "persistentId": bng.pid(), "__parent": GROUP} for s in subgroups]
    for s in subgroups:
        files[f"{lv}/main/MissionGroup/{GROUP}/{s}/items.level.json"] = (
            "\n".join(json.dumps(o, separators=(",", ":")) for o in objs if o["__parent"] == s) + "\n").encode("utf-8")
    # the group in MissionGroup/items.level.json, its subgroups in its own, the emitters in theirs
    mg = f"{lv}/main/MissionGroup/items.level.json"
    top = read_items(zi, mg) if mg in zi.NameToInfo else []
    top = [r for r in top if r.get("name") != GROUP]
    top.append(rows[0])
    files[mg] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in top) + "\n").encode("utf-8")
    files[f"{lv}/main/MissionGroup/{GROUP}/items.level.json"] = (
        "\n".join(json.dumps(o, separators=(",", ":")) for o in rows[1:]) + "\n").encode("utf-8")
    old = [n for n in zi.namelist() if n.startswith(f"{lv}/main/MissionGroup/{GROUP}/")]
    now = time.localtime()[:6]
    with zi.writer() as zo:
        for i in zi.infolist():
            if i.filename not in files and i.filename not in old:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for nm, data in sorted(files.items()):
            zo.writestr(zipfile.ZipInfo(nm, now), data, compress_type=zipfile.ZIP_DEFLATED)
    rep["seconds"] = round(time.time() - t0)
    print("ambient sounds:", json.dumps(rep), flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--scan":
        scan(sys.argv[2])
    else:
        print("python ambient_sounds.py --scan <BeamNG.drive folder>   (the step itself: build_level.py --finish ambient_sounds)")
