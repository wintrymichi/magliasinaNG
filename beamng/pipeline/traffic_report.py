"""What the in-game traffic test (bng_lua/magliaso_traffic.lua) found, as numbers (v3.0.40, a development aid):
the game's AI graph (nodes, links, which fields its links carry, km per speed limit, pieces not linked to the main
one) and the traffic cars that stood still for STUCK_S s or more away from a stop line, with where.
    python traffic_report.py <magliaso_traffic folder from the user folder> [--out report.json]
"""
import json, os, sys
from collections import Counter, defaultdict
import numpy as np

STUCK_S = 20.0      # standing this long counts as stuck
STILL_MS = 0.5      # m/s below which a car stands
JUMP_M = 40.0       # m between two samples: the traffic moved (respawned) the car
CRASH = 500.0       # rise of the game's damage value between two samples that counts as a crash


def graph(nav):
    nodes = nav["nodes"]
    pos = {k: np.array(v["pos"], float) for k, v in nodes.items()}
    fields, limits, km = Counter(), defaultdict(float), 0.0
    adj = defaultdict(set)
    for a, v in nodes.items():
        for b, link in v["links"].items():
            if b not in pos:
                continue
            adj[a].add(b)
            adj[b].add(a)
            if a > b:            # each link is listed from both ends
                continue
            d = float(np.linalg.norm(pos[a][:2] - pos[b][:2])) / 1000.0
            km += d
            fields.update(link.keys())
            lim = link.get("speedLimit")
            limits["none" if lim is None else str(round(float(lim) * 3.6))] += d
    seen, pieces = set(), []
    for s in nodes:
        if s in seen:
            continue
        stack, part = [s], []
        seen.add(s)
        while stack:
            n = stack.pop()
            part.append(n)
            for m in adj[n] - seen:
                seen.add(m)
                stack.append(m)
        pieces.append(part)
    pieces.sort(key=len, reverse=True)
    off = [p for p in pieces[1:] if len(p) > 1]
    return {"nodes": len(nodes), "km": round(km, 1), "link_fields": dict(fields),
            "km_per_limit_kmh": {k: round(v, 1) for k, v in sorted(limits.items())},
            "pieces": len(pieces), "main_piece_nodes": len(pieces[0]) if pieces else 0,
            "off_main_pieces": [{"nodes": len(p), "at": [round(x, 1) for x in pos[p[0]][:2]]} for p in off[:40]],
            "dead_ends": sum(1 for n in nodes if len(adj[n]) == 1)}


def stuck(samples):
    tracks = defaultdict(list)
    for rows in samples:
        for r in rows:
            tracks[r["id"]].append(r)
    out = []
    for vid, rs in tracks.items():
        start = None
        for r in rs + [None]:
            still = r is not None and r["v"] < STILL_MS
            if still and start is None:
                start = r
            elif not still and start is not None:
                last = prev
                if last["t"] - start["t"] >= STUCK_S:
                    out.append({"vehicle": vid, "model": start.get("model"), "from_s": start["t"],
                                "for_s": last["t"] - start["t"], "x": round(start["x"], 1), "y": round(start["y"], 1),
                                "road": [start.get("a"), start.get("b")], "off_road_m": start.get("d"),
                                "state": start.get("state")})
                start = None
            prev = r
    out.sort(key=lambda s: -s["for_s"])
    # respawns (a jump of over JUMP_M between two samples) and crashes (damage rising by over CRASH)
    jumps, crashes = [], []
    for vid, rs in tracks.items():
        for a, b in zip(rs, rs[1:]):
            if np.hypot(b["x"] - a["x"], b["y"] - a["y"]) > JUMP_M:
                jumps.append({"vehicle": vid, "t": b["t"], "from": [round(a["x"], 1), round(a["y"], 1)],
                              "v_before": round(a["v"], 1)})
            da, db = a.get("damage") or 0, b.get("damage") or 0
            if db - da > CRASH:
                crashes.append({"vehicle": vid, "t": b["t"], "x": round(b["x"], 1), "y": round(b["y"], 1),
                                "damage": round(db - da), "v_before": round(a["v"], 1), "road": [a.get("a"), a.get("b")]})
    moved = {vid: float(sum(np.hypot(b["x"] - a["x"], b["y"] - a["y"]) for a, b in zip(rs, rs[1:])) / 1000.0)
             for vid, rs in tracks.items()}
    return {"vehicles": len(tracks), "km_driven": round(sum(moved.values()), 1),
            "stuck": out, "stuck_places": len({(round(s["x"] / 20), round(s["y"] / 20)) for s in out}),
            "respawns": len(jumps), "crashes": len(crashes), "respawn_list": jumps[:200], "crash_list": crashes[:200]}


def main(argv):
    src = argv[0]
    rep = {}
    p = os.path.join(src, "navgraph.json")
    if os.path.exists(p):
        rep["graph"] = graph(json.load(open(p)))
    p = os.path.join(src, "traffic.json")
    if os.path.exists(p):
        rep["traffic"] = stuck(json.load(open(p)))
    p = os.path.join(src, "parking.json")
    if os.path.exists(p):
        rep["parking"] = json.load(open(p)).get("spots")
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(src, "report.json")
    json.dump(rep, open(out, "w"), indent=1)
    print(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk not in ("off_main_pieces", "stuck", "respawn_list", "crash_list")}
                          if isinstance(v, dict) else v) for k, v in rep.items()}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
