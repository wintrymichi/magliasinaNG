"""Independent tiles of a finishing step in forked worker processes (switzerlandNG faster builds, 2026-11-09).

A step that walks the terrain block tile by tile, where each tile reads only what the step loaded before the loop and
returns its own pieces, hands the tiles to imap(): the workers are forked after the loading, so they share its arrays
(copy-on-write) and nothing big is pickled on the way in; the results come back in tile order, and the step merges
them as its sequential loop did. The level written is the same as with one process (the tests compare them).

TILE_WORKERS sets the number of processes (the app sets it from the PC's memory and cores, system.workers); 1, or a
system without fork (Windows), runs the tiles in the step's own process, one after the other.
"""
import os
import sys

STATE = None              # what the step loaded, for the workers (inherited by the fork)
_FN = None


def workers(default=4):
    if not hasattr(os, "fork"):
        return 1
    n = os.environ.get("TILE_WORKERS")
    try:
        n = int(n) if n else min(default, os.cpu_count() or 1)
    except ValueError:
        n = 1
    return max(1, n)


def _call(item):
    return _FN(STATE, item)


def imap(fn, items, state, n=None, chunksize=1):
    """fn(state, item) for every item, in the order of items; in n forked processes when n > 1."""
    global STATE, _FN
    items = list(items)
    n = workers() if n is None else n
    STATE, _FN = state, fn
    try:
        if n <= 1 or len(items) < 2:
            for it in items:
                yield fn(state, it)
            return
        import multiprocessing as mp
        sys.stdout.flush()
        sys.stderr.flush()
        with mp.get_context("fork").Pool(min(n, len(items))) as pool:
            for r in pool.imap(_call, items, chunksize):
                yield r
    finally:
        STATE, _FN = None, None


def merge_report(rep, part):
    """A tile's counts into the step's report as the sequential loop added them: keys with "max" in the name take
    the larger value, the others add up; new keys in the order they first appear."""
    for k, v in part.items():
        if k not in rep:
            rep[k] = v
        elif "max" in k:
            rep[k] = max(rep[k], v)
        else:
            rep[k] = rep[k] + v
    return rep
