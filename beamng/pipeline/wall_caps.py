"""Photo check of the height of the cadastral walls near the road.

The LiDAR crest of a wall also catches what stands on it or hangs over it (guardrails,
railings, shrubs, the roof or balcony of the house behind), which turned 1 m garden walls
into 3-7 m slabs and valley-side retaining walls into parapets. For every wall vertex within
15 m of the road whose top is more than 0.3 m above its base, points just in front of the
wall at LEVELS above the base (up to the modelled top) are checked in the segmented
panoramas (photo_votes.label_votes, panoramas 1.2-16 m away). Going up, the visible wall ends
at the first level where 'Wall' falls below 30 % of >= 2 votes (railing, hedge, facade, sky
seen instead). The top is capped half-way between that level and the last wall level. Where
the photos do not see a level (too few votes) the LiDAR height is kept.
For valley-side walls the base is the road surface next to the wall (the face below the
road is not seen from it). A wall with no wall votes at the two lowest levels is capped at
the base +0.15 m (kerb), unless plants cover it. Parked cars, people and 'Building' (stone walls are
often labelled so; a facade behind a low wall too) are not counted as votes. The heights are then smoothed along each wall (median over +-4 vertices, ~2 m), so
single vertices neither spike nor notch.
Output: work/wall_caps.json {"x,y": z_cap} (vertex coordinates rounded to cm).
"""
import json, os
import numpy as np
import shapely
from config import WORK
import walls, roadheight, photo_votes

WALL, VEG = 6, 30
# votes that say nothing about the wall: parked cars and people hide it, and the segmenter
# labels stone walls as 'Building' as often as the house facade behind a garden wall
OCCLUDERS = [17, 19, 20, 21, 22] + list(range(52, 63)) + [63, 64]
LEVELS = np.array([0.35, 0.65, 0.95, 1.3, 1.7, 2.2, 2.8, 3.5, 4.5, 6.0])
NEAR_ROAD = 15.0


def main():
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    line = shapely.LineString(rp["center"])
    fn = roadheight.height_fn()
    ctx = walls._context()
    ctx["caps"] = {}                                         # measure the uncapped geometry
    cand = []                                                # (xy, base z, top z, unit towards the road)
    for w in walls.wall_geometry(ctx):
        if w["poly"].distance(line) > NEAR_ROAD:
            continue
        V = w["allv"]
        sv = shapely.line_locate_point(line, shapely.points(V))
        C = shapely.get_coordinates(shapely.line_interpolate_point(line, sv))
        d = V - C
        dist = np.linalg.norm(d, axis=1)
        u = -d / np.maximum(dist[:, None], 1e-6)
        zr = fn((V + u * 0.3)[:, 0], (V + u * 0.3)[:, 1])     # road / ground surface on the road side
        # base seen from the road: the higher of the wall foot and the surface in front of it
        base = np.maximum(w["zlo"], np.minimum(zr, w["ztop"] - 0.05))
        for j in np.where(w["ztop"] > base + 0.3)[0]:
            cand.append((V[j], base[j], w["ztop"][j], u[j], w["key"]))
    print("wall vertices near the road to check:", len(cand))
    pts, owner, lev = [], [], []
    for i, (v, zb, zt, u, _) in enumerate(cand):
        for k, h in enumerate(LEVELS):
            if zb + h < zt - 0.05:
                pts.append([v[0] + u[0] * 0.12, v[1] + u[1] * 0.12, zb + h]); owner.append(i); lev.append(k)
    # the nearest panorama sees a roadside wall frontally from ~1.5 m: include it
    H = photo_votes.label_votes(np.array(pts), d_min=1.2)
    owner, lev = np.array(owner), np.array(lev)
    tot = H.sum(1) - H[:, OCCLUDERS].sum(1)
    wall, veg = H[:, WALL], H[:, VEG]
    order = np.lexsort((lev, owner))
    starts = np.searchsorted(owner[order], np.arange(len(cand)))
    ends = np.searchsorted(owner[order], np.arange(len(cand)), side="right")
    rel = np.array([c[2] - c[1] for c in cand])          # height above the base, LiDAR
    n_cut = n_kerb = n_keep = 0
    for i, (v, zb, zt, u, key) in enumerate(cand):
        idx = order[starts[i]:ends[i]]
        top_ok, cut = -1, None
        for q in idx:
            if tot[q] < 2:
                break                                        # not seen: keep the LiDAR height above
            if wall[q] >= 0.3 * tot[q]:
                top_ok = lev[q]
            else:
                cut = lev[q]
                break
        if cut is None:
            n_keep += 1
            continue
        if top_ok < 0:
            # no wall at all above the base: only when both lowest levels are seen, and not
            # because plants cover the face
            low = idx[:2]
            seen_low = all(tot[q] >= 2 and wall[q] < 0.3 * tot[q] and veg[q] < 0.5 * tot[q] for q in low)
            if not seen_low or (len(low) < 2 and zt - zb > LEVELS[1] + 0.05):
                n_keep += 1
                continue
            rel[i] = 0.15
            n_kerb += 1
        else:
            rel[i] = 0.5 * (LEVELS[top_ok] + LEVELS[cut])
            n_cut += 1
    # walls are continuous structures: median of the heights over +-4 vertices (~2 m) along
    # each wall removes single-vertex spikes and notches
    from scipy.ndimage import median_filter
    per_wall = {}
    for i, c in enumerate(cand):
        per_wall.setdefault(c[4], []).append(i)
    caps = {}
    for key, ii in per_wall.items():
        ii = np.array(ii)
        f = median_filter(rel[ii], size=9, mode="nearest") if len(ii) >= 3 else rel[ii]
        for i, h in zip(ii, f):
            v, zb, zt = cand[i][0], cand[i][1], cand[i][2]
            if zb + h < zt - 0.05:
                caps["%.2f,%.2f" % (v[0], v[1])] = round(float(zb + h), 3)
    json.dump(caps, open(os.path.join(WORK, "wall_caps.json"), "w"))
    print("photos see the wall end:", n_cut, "| no wall above the base (kerb):", n_kerb,
          "| kept (wall seen to the top or not visible):", n_keep, "| vertices capped after smoothing:", len(caps))


if __name__ == "__main__":
    main()
