"""The views of the in-game test of the whole v2.8 zip (run_v28_screenshots.ps1, beamng/verifica/v2.8/final_test_plan.md).
    python v28_tour.py views <zip> <tag>   -> <user>/magliaso_unpaved_views.json
The views of the nine v2.8 checks one after the other (their sites.json in beamng/verifica/v2.8/<topic>/), every name
prefixed with its topic, every view by day except the street lamps at night, which come last: the extension
(bng_lua/magliaso_unpaved.lua) keeps the time of day of the view before.
"""
import json, os, sys
import catenary_tour, houses_tour, lake_tour, lamps_tour, paved_tour, roadside_tour, signs_more_tour, understory_tour
import wall_fill_tour

TOURS = (("paved_edges", paved_tour), ("wall_fill", wall_fill_tour), ("understory", understory_tour),
         ("lamps", lamps_tour), ("roadside", roadside_tour), ("catenary", catenary_tour), ("signs", signs_more_tour),
         ("lake", lake_tour), ("houses", houses_tour))
VIEWS = paved_tour.VIEWS


def views(zp, tag):
    day, night = [], []
    for topic, mod in TOURS:
        assert mod.VIEWS == VIEWS
        mod.views(zp, tag)
        for v in json.load(open(VIEWS)):
            v["name"] = f"{topic}_{v['name']}"
            v["fps"] = True
            (night if v.get("tod", 0.0) else day).append(dict(v, tod=v.get("tod", 0.0)))
    out = day + night
    json.dump(out, open(VIEWS, "w"), indent=1)
    print(VIEWS, len(out), "views", len(night), "at night")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"views": views}[cmd](*args)
