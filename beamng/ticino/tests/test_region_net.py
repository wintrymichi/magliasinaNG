"""region_net: a road across a core edge, cut in both zones and welded into one shared point."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import region_net  # noqa: E402


class Z:
    def __init__(self, name, core):
        self.name, self.core = name, core

    def in_core(self, x, y):
        x0, y0, x1, y1 = self.core
        return x0 <= x < x1 and y0 <= y < y1


def test_cut_and_weld():
    a, b = Z("a", (0, 0, 100, 100)), Z("b", (100, 0, 200, 100))
    road = {"class": "DecalRoad", "name": "r", "drivability": 1,
            "nodes": [[90, 50, 10, 6], [99.8, 50.2, 10.5, 6], [110, 52, 11, 7]]}
    pa = region_net.cut_road(road, a)
    pb = region_net.cut_road(road, b)
    assert len(pa) == len(pb) == 1
    (oa, a0, a1), (ob, b0, b1) = pa[0], pb[0]
    assert (a0, a1, b0, b1) == (False, True, True, False)
    assert abs(oa["nodes"][-1][0] - 100) < 1e-9 and abs(ob["nodes"][0][0] - 100) < 1e-9
    assert len(oa["nodes"]) == 2               # the node 0.2 m from the edge gave way to the cut point
    ob["nodes"][0][1] += 0.3                   # the neighbour built it a little apart
    st = region_net.weld([(oa, "a", a0, a1), (ob, "b", b0, b1)])
    assert st["welded"] == 2 and oa["nodes"][-1] == ob["nodes"][0]
    rep = region_net.graph_report([oa, ob])
    assert rep["pieces"] == 1 and rep["dead_ends"] == 2


def test_along_edge_once():
    a, b = Z("a", (0, 0, 100, 100)), Z("b", (100, 0, 200, 100))
    road = {"nodes": [[100, 10, 0, 4], [100, 40, 0, 4]], "name": "e"}
    assert len(region_net.cut_road(road, a)) + len(region_net.cut_road(road, b)) == 1


if __name__ == "__main__":
    test_cut_and_weld()
    test_along_edge_once()
    print("ok")
