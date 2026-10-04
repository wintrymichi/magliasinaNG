"""Where the road signs of the network stand, from OpenStreetMap (v2.7): which signs, at which point of
the road, for which direction of travel. patch_signs.py puts them beside the carriageway.

Two kinds of source, kept apart in the output (src):
- "osm": the signs mapped one by one in OpenStreetMap (traffic_sign=CH:..., city_limit, maxspeed, a
  description of the sign), at the mapped point, facing the mapped direction;
- "rule": the signs the Swiss rules put where OpenStreetMap records the regulation they announce,
  but not the sign itself:
    * a speed limit that changes along a road (maxspeed of two consecutive ways): 2.30 for the new
      limit; on a main road entering a 50 limit, 2.30.1 "generale" over the beginning of the village
      (4.27 with the commune's name where the commune is a single village, else no name plate);
      leaving it, 2.53.1 (to the general 80) or 2.30 for the new limit over 4.28. The same order as
      the signs mapped in Magliaso (traffic_sign=CH:2.30.1[50];4.27[Caslano]);
    * a 30 zone (maxspeed 30 on a minor road, or source:maxspeed=CH:zone30): 2.59.1 at every road into
      it, 2.59.2 at every road out of it; a meeting zone (20 on a minor road): 2.59.3 / 2.59.4;
    * a one-way street: 4.08 where it begins, 2.02 against the traffic where it ends;
    * a marked pedestrian crossing (zebra) on a road: 4.11 on the right for both directions;
    * a roundabout: 2.41.1 over the give-way 3.02 at every road into it.
  A rule sign is left out where an "osm" sign of the same kind stands within DEDUP m for the same
  direction (the mapped one wins), and STOP / give-way stay those of props_osm.py (already in the level).

    plan() -> [Sign]
(c) OpenStreetMap contributors, ODbL.
"""
import gzip, json, math, os, re
from collections import namedtuple
import numpy as np
import shapely
import osm
import signs_ch
from config import wgs_to_local

# x, y: the point of the road (or the mapped point); u: unit vector of the traffic that reads it;
# plates: [(code, value)] top to bottom; mapped: the OSM node is where the sign stands (not on the road);
# limit: the speed limit where it stands (mounting height); big: main road outside villages
Sign = namedtuple("Sign", "x y u plates src osm_id kind limit big mapped")
DEDUP = 60.0
MINOR = {"residential", "living_street", "unclassified", "service", "road"}
MAIN = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link", "trunk", "trunk_link"}
SIGN_ROADS = MAIN | MINOR - {"service"} | {"motorway", "motorway_link"}
DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
# communes whose only village carries their name: the beginning-of-village sign can be named
MERGED = {"Alto Malcantone", "Tresa", "Lema", "Bioggio", "Lugano", "Collina d'Oro", "Capriasca"}


def _num(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _unit(v):
    n = math.hypot(v[0], v[1])
    return np.array([v[0] / n, v[1] / n]) if n > 1e-9 else None


def bearing_vec(deg):
    """Unit vector (east, north) of a compass bearing in degrees."""
    a = math.radians(float(deg))
    return np.array([math.sin(a), math.cos(a)])


def communes():
    """[(name, local polygon)] of the Swiss municipalities (dati/osm_communes.json.gz)."""
    f = os.path.join(DATI, "osm_communes.json.gz")
    if not os.path.exists(f):
        return []
    out = []
    for e in json.load(gzip.open(f, "rt", encoding="utf-8"))["elements"]:
        t = e.get("tags", {})
        if not (t.get("ref:bfs_Gemeindenummer") or t.get("swisstopo:BFS_NUMMER")):
            continue
        rings = []
        for m in e.get("members", []):
            if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry"):
                lat = np.array([q["lat"] for q in m["geometry"]])
                lon = np.array([q["lon"] for q in m["geometry"]])
                x, y = wgs_to_local(lat, lon)
                rings.append(shapely.LineString(np.column_stack([x, y])))
        polys = shapely.polygonize(rings)
        if not polys.is_empty:
            out.append((t.get("name", ""), shapely.union_all(list(polys.geoms))))
    return out


class Net:
    """The drivable OSM ways and their junctions."""

    def __init__(self, ways):
        self.w = [w for w in ways if w["tags"].get("highway") in osm.DRIVE]
        self.at = {}                                     # node -> [(way index, vertex index)]
        for i, w in enumerate(self.w):
            for k, nd in enumerate(w["nodes"]):
                self.at.setdefault(nd, []).append((i, k))

    def degree(self, nd):
        return sum(1 if k in (0, len(self.w[i]["nodes"]) - 1) else 2 for i, k in self.at.get(nd, []))

    def oneway(self, i):
        """+1 / -1 for a one-way way along / against its vertices, 0 for both directions."""
        t = self.w[i]["tags"]
        o = t.get("oneway")
        if o in ("yes", "1", "true") or t.get("junction") == "roundabout" or t.get("highway") in ("motorway",):
            return 1
        return -1 if o == "-1" else 0

    def dir_at(self, i, k, sgn, step=6.0):
        """Unit travel vector leaving vertex k of way i along (+1) or against (-1) its vertices, about
        `step` m ahead (a point of the line, not just the next vertex)."""
        w = self.w[i]
        line = w["line"]
        s = line.project(shapely.Point(w["xy"][k]))
        s2 = min(max(s + sgn * step, 0.0), line.length)
        p = np.asarray(line.interpolate(s2).coords[0])
        return _unit(p - w["xy"][k])

    def point(self, i, k, sgn, dist):
        """Point `dist` m from vertex k of way i, along (+1) or against (-1) the way."""
        w = self.w[i]
        line = w["line"]
        s = line.project(shapely.Point(w["xy"][k]))
        return np.asarray(line.interpolate(min(max(s + sgn * dist, 0.0), line.length)).coords[0])

    def can_drive(self, i, sgn):
        o = self.oneway(i)
        return o == 0 or o == sgn


def _limit(tags):
    v = tags.get("maxspeed")
    if v in ("walk",):
        return 5
    return _num(v)


def _zone(tags):
    """'30' / '20' when the way is in a 30 zone / meeting zone, else None."""
    hw = tags.get("highway")
    src = (tags.get("source:maxspeed") or tags.get("maxspeed:type") or tags.get("zone:maxspeed") or "").lower()
    v = _limit(tags)
    if "zone30" in src or src == "ch:30":
        return "30"
    if hw in MINOR and v == 30:
        return "30"
    if hw in MINOR | {"living_street"} and v == 20:
        return "20"
    return None


def explicit(nodes, net):
    """Signs mapped one by one in OSM."""
    out = []
    tree = shapely.STRtree([w["line"] for w in net.w])
    for n in nodes:
        t = n["tags"]
        ts = t.get("traffic_sign")
        if not ts:
            continue
        p = np.array([n["x"], n["y"]])
        groups = []
        if ts.startswith("CH:"):
            groups = signs_ch.parse(ts)
        elif ts == "city_limit" and t.get("name"):
            groups = "city_limit"
        elif ts == "maxspeed" and _num(t.get("maxspeed")):
            groups = [[("2.30", str(_num(t["maxspeed"])))]]
        elif ts == "maxlength" and t.get("maxlength"):
            groups = [[("2.20", t["maxlength"])]]
        elif ts == "yes" and t.get("description"):
            groups = _from_description(t["description"])
        if not groups:
            continue
        # the road it stands by, the travel direction that reads it
        j = tree.nearest(shapely.Point(p))
        w = net.w[j]
        q = np.asarray(shapely.shortest_line(w["line"], shapely.Point(p)).coords)[0]
        s = w["line"].project(shapely.Point(q))
        a = np.asarray(w["line"].interpolate(max(s - 3, 0)).coords[0])
        b = np.asarray(w["line"].interpolate(min(s + 3, w["line"].length)).coords[0])
        tng = _unit(b - a)
        if tng is None:
            continue
        d = t.get("direction")
        dirs = []
        if d in ("forward", "backward"):
            dirs = [tng if d == "forward" else -tng]
        elif d is not None and re.fullmatch(r"\d+(\.\d+)?", d.strip()):
            u = -bearing_vec(d)                              # the plate faces `direction`: traffic comes the other way
            dirs = [tng if np.dot(u, tng) >= 0 else -tng]
        else:
            o = net.oneway(j)
            dirs = [tng * o] if o else [tng, -tng]
        big = w["tags"].get("highway") in ("motorway", "motorway_link", "trunk")
        lim = _limit(w["tags"])
        if groups == "city_limit":
            main = w["tags"].get("highway") in MAIN
            cl = t.get("city_limit")
            for u in dirs:
                if cl in ("begin", "end"):
                    code = ("4.27" if cl == "begin" else "4.28") if main else ("4.29" if cl == "begin" else "4.30")
                else:                                      # both faces: begin for the traffic going into the village
                    code = None
                    inside = _village_side(net, p, u)
                    if inside is None:
                        continue
                    code = ("4.27" if inside else "4.28") if main else ("4.29" if inside else "4.30")
                out.append(Sign(q[0], q[1], u, [(code, t["name"])], "osm", n["id"], "city_limit", lim, False, False))
            continue
        if t.get("highway") in ("stop", "give_way"):          # already built by props_osm.py
            groups = [[pl for pl in g if pl[0] not in ("3.01", "3.02")] for g in groups]
            groups = [g for g in groups if g]
        plates = [pl for g in groups for pl in _expand(g)]
        if not plates:
            continue
        kind = "+".join(c for c, _ in plates)
        # the mapped point is the sign itself where it stands off the road axis
        mapped = float(np.hypot(*(p - q))) > 1.5
        for u in dirs:
            out.append(Sign(p[0] if mapped else q[0], p[1] if mapped else q[1], u, plates, "osm", n["id"], kind,
                            lim, big, mapped))
    return out


def _expand(group):
    """The plates of one signal and the plates under it: 2.30.1 -> 2.30 over 'generale'; unknown
    codes dropped (an unknown main signal drops its plates too)."""
    out = []
    for i, (code, val) in enumerate(group):
        if code in signs_ch.GENERAL:
            base = signs_ch.GENERAL[code]
            if signs_ch.known(base, val or "50"):
                out += [(base, val or "50"), ("text", "generale")]
            elif i == 0:
                return []
            continue
        if code.startswith("5.") and not signs_ch.known(code, val):
            if val:
                out.append(("text", val))
            continue
        if signs_ch.known(code, val):
            out.append((code, val))
            if val and code in ("2.01", "2.02", "2.03", "2.05", "2.59.3", "2.59.1") and not _num(val):
                out.append(("text", val.replace("Eccezione:", "Eccezione: ").replace("  ", " ")))
        elif i == 0:
            return []
    return out


def _from_description(desc):
    """The signal a free-text OSM description names (the mappers of the area write them in Italian)."""
    d = desc.lower()
    if "divieto di transito" not in d:
        return []
    code = "2.05" if "bicicl" in d else "2.01"
    g = [(code, None)]
    m = re.search(r"\ba\s*(\d+)\s*m\b", d)
    if "preavviso" in d and m:
        g.append(("5.01", f"{m.group(1)} m"))
    m = re.search(r"\"([^\"]+)\"", desc)
    if m:
        g.append(("text", m.group(1)))
    return [g]


def _village_side(net, p, u):
    """True when travelling along u from p goes into the denser network (the village), False out of
    it, None when it cannot be told."""
    ahead, behind = p + u * 200, p - u * 200
    junctions = getattr(net, "_junc", None)
    if junctions is None:
        js = []
        for nd, occ in net.at.items():
            if net.degree(nd) >= 3:
                i, k = occ[0]
                js.append(net.w[i]["xy"][k])
        net._junc = junctions = np.array(js)
    na = int((np.hypot(*(junctions - ahead).T) < 180).sum())
    nb = int((np.hypot(*(junctions - behind).T) < 180).sum())
    if na == nb:
        return None
    return na > nb


def rules(net, comm):
    """Signs the regulation implies (see the module docstring)."""
    out = []
    ctree = shapely.STRtree([g for _, g in comm]) if comm else None

    def commune_at(x, y):
        if ctree is None:
            return None
        hit = ctree.query(shapely.Point(x, y), predicate="within")
        return comm[hit[0]][0] if len(hit) else None

    def add(p, u, plates, kind, lim, big=False):
        out.append(Sign(float(p[0]), float(p[1]), u, plates, "rule", None, kind, lim, big, False))

    for nd, occ in net.at.items():
        deg = net.degree(nd)
        # every pair (a way into the node, a way out of it)
        ends = []                                       # (way, vertex, sgn of travel leaving the node)
        for i, k in occ:
            n = len(net.w[i]["nodes"])
            if k < n - 1:
                ends.append((i, k, 1))
            if k > 0:
                ends.append((i, k, -1))
        for (ia, ka, sa) in ends:                       # arriving along way ia (travel -sa at the node)
            if not net.can_drive(ia, -sa):
                continue
            ta = net.w[ia]["tags"]
            for (ib, kb, sb) in ends:
                if ib == ia and kb == ka:
                    continue
                if not net.can_drive(ib, sb):
                    continue
                tb = net.w[ib]["tags"]
                hb = tb.get("highway")
                if hb not in SIGN_ROADS:
                    continue
                u = net.dir_at(ib, kb, sb)
                if u is None:
                    continue
                za, zb = _zone(ta), _zone(tb)
                va, vb = _limit(ta), _limit(tb)
                # only between roads whose limits are both mapped, and not from or into a yard or track
                if va is None or vb is None or ta.get("highway") not in SIGN_ROADS:
                    continue
                # zones: into / out of
                if zb and zb != za:
                    code = "2.59.1" if zb == "30" else "2.59.3"
                    add(net.point(ib, kb, sb, 4.0), u, [(code, zb if zb == "30" else None)], code, int(zb))
                    continue
                if za and not zb and hb in SIGN_ROADS:
                    code = "2.59.2" if za == "30" else "2.59.4"
                    add(net.point(ib, kb, sb, 4.0), u, [(code, za if za == "30" else None)], code, vb or 50)
                    continue
                # a limit that changes along the same road
                same = deg == 2 or (tb.get("name") and tb.get("name") == ta.get("name")) or \
                       (tb.get("ref") and tb.get("ref") == ta.get("ref"))
                if not same or va == vb or za or zb:
                    continue
                if hb in ("motorway", "motorway_link", "trunk_link") or vb < 30:
                    continue
                p = net.point(ib, kb, sb, 3.0)
                main = hb in MAIN
                if vb == 50 and va > 50 and main:
                    name = commune_at(*p)
                    plates = [("4.27", name)] if name and name not in MERGED else []
                    add(p, u, [("2.30", "50"), ("text", "generale")] + plates, "village_begin", 50)
                elif va == 50 and vb > 50 and main:
                    name = commune_at(*net.w[ia]["xy"][ka])
                    plates = [("4.28", name)] if name and name not in MERGED else []
                    tail = [("2.53", "50"), ("text", "generale")] if vb == 80 else [("2.30", str(vb))]
                    add(p, u, tail + plates, "village_end", vb, big=vb >= 80)
                else:
                    add(p, u, [("2.30", str(vb))], "2.30", vb, big=vb >= 80 and main)
        # one-way streets: 4.08 at the start, 2.02 at the end (the traffic that would go in against it)
        for i, k in occ:
            w = net.w[i]
            o = net.oneway(i)
            hw = w["tags"].get("highway")
            if not o or w["tags"].get("junction") == "roundabout" or hw not in (MINOR | {"tertiary"}) - {"service"}:
                continue
            n = len(w["nodes"])
            first = (k == 0 and o == 1) or (k == n - 1 and o == -1)
            last = (k == n - 1 and o == 1) or (k == 0 and o == -1)
            others = [(j, kk) for j, kk in occ if j != i]
            if not others:
                continue
            # a one-way chain continuing through the node is not its beginning or end
            if any(net.oneway(j) and net.w[j]["tags"].get("highway") == hw for j, _ in others):
                continue
            if first:
                u = net.dir_at(i, k, o)
                if u is not None:
                    add(net.point(i, k, o, 5.0), u, [("4.08", None)], "4.08", _limit(w["tags"]) or 50)
            if last:
                u = net.dir_at(i, k, -o)
                if u is not None:
                    add(net.point(i, k, -o, 3.0), u, [("2.02", None)], "2.02", _limit(w["tags"]) or 50)
        # roundabouts: 2.41.1 over 3.02 on every road into the ring
        ring = [i for i, _ in occ if net.w[i]["tags"].get("junction") == "roundabout"]
        if ring:
            for i, k in occ:
                if i in ring:
                    continue
                n = len(net.w[i]["nodes"])
                for sgn in ((1,) if k == 0 else ()) + ((-1,) if k == n - 1 else ()):
                    if not net.can_drive(i, -sgn):            # traffic must be able to arrive at the ring
                        continue
                    u = -net.dir_at(i, k, sgn)
                    add(net.point(i, k, sgn, 4.0), u, [("2.41.1", None), ("3.02", None)], "roundabout",
                        _limit(net.w[i]["tags"]) or 50)
    return out


def crossings(nodes, net):
    """4.11 for both directions at the marked pedestrian crossings of the roads (not at traffic lights,
    not in a zone)."""
    out = []
    for n in nodes:
        t = n["tags"]
        if t.get("highway") != "crossing":
            continue
        c, m, ref = t.get("crossing"), t.get("crossing:markings"), t.get("crossing_ref")
        if c in ("traffic_signals", "unmarked", "no", "informal") or m == "no":
            continue
        if not (c in ("zebra", "marked", "uncontrolled") or ref == "zebra" or m in ("zebra", "yes")):
            continue
        for i, k in net.at.get(n["id"], []):
            w = net.w[i]
            if w["tags"].get("highway") not in SIGN_ROADS or _zone(w["tags"]):
                continue
            for sgn in (1, -1):
                if not net.can_drive(i, sgn):
                    continue
                u = net.dir_at(i, k, sgn)
                if u is None:
                    continue
                p = net.point(i, k, -sgn, 1.0)            # just before the stripes
                out.append(Sign(float(p[0]), float(p[1]), u, [("4.11", None)], "rule", n["id"], "4.11",
                                _limit(w["tags"]) or 50, False, False))
            break
    return out


def _dedup(signs):
    """A rule sign goes where no mapped sign of the same kind stands for the same direction within
    DEDUP m, and once per kind and direction within 25 m."""
    keep = []
    mapped = [s for s in signs if s.src == "osm"]
    for s in signs:
        if s.src == "osm":
            keep.append(s)
            continue
        codes = {c for c, _ in s.plates}
        clash = False
        for o in mapped:
            if np.hypot(o.x - s.x, o.y - s.y) < DEDUP and np.dot(o.u, s.u) > 0.5 and codes & {c for c, _ in o.plates} - {"text"}:
                clash = True
                break
        if not clash:
            for o in keep:
                if o.src == "rule" and o.kind == s.kind and np.hypot(o.x - s.x, o.y - s.y) < 25 and np.dot(o.u, s.u) > 0.5:
                    clash = True
                    break
        if not clash:
            keep.append(s)
    return keep


def plan():
    ways, nodes = osm.load()
    net = Net(ways)
    signs = explicit(nodes, net) + rules(net, communes()) + crossings(nodes, net)
    return _dedup(signs)


if __name__ == "__main__":
    from collections import Counter
    S = plan()
    print(len(S), Counter(s.src for s in S))
    print(Counter(s.kind for s in S).most_common(40))
