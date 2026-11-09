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


# ---------------------------------------------------------------------------------------------- pmap
# multiprocessing.Pool waits for ever when one of its workers dies (the OOM killer, 2026-10-17 and the reviewer's
# reproduction of 2026-11-09): the task is lost and the Pool only starts a new worker. pmap runs on
# concurrent.futures.ProcessPoolExecutor, which notices a dead worker (BrokenProcessPool): the items not done yet run
# again with half the workers, down to the step's own process, one after the other; the order of the results stays.
# Workers that live but do nothing (a lock inherited across the fork) are caught too: no result for POOL_STALL s and
# almost no CPU in the workers in that time.
POOL_STALL = float(os.environ.get("MAGLIASO_POOL_STALL", "900"))
_JOB = None                    # (fn, items) for the forked workers: only indices go through the pipes


def _run_chunk(idx):
    fn, items = _JOB
    return [(i, fn(items[i])) for i in idx]


def _run_pickled(fn, pairs):
    return [(i, fn(it)) for i, it in pairs]


def cpu_seconds(pid):
    """CPU time of a process (psutil, or /proc on Linux), None when it cannot be told."""
    try:
        import psutil
        c = psutil.Process(pid).cpu_times()
        return c.user + c.system
    except ImportError:
        pass
    except Exception:
        return 0.0
    try:
        with open("/proc/%d/stat" % pid) as f:
            v = f.read().rsplit(")", 1)[1].split()
        return (int(v[11]) + int(v[12])) / os.sysconf("SC_CLK_TCK")
    except FileNotFoundError:
        return 0.0
    except Exception:
        return None


def _workers_cpu(ex):
    t = 0.0
    for p in list(getattr(ex, "_processes", {}).values()):
        c = cpu_seconds(p.pid)
        if c is None:
            return None
        t += c
    return t


def _kill(ex):
    for p in list(getattr(ex, "_processes", {}).values()):
        try:
            p.kill()
        except Exception:
            pass
    try:
        ex.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    # the next pool forks: no thread of this one may be running then (a child would inherit a lock it holds)
    t = getattr(ex, "_executor_manager_thread", None)
    if t is not None:
        t.join(10)
    for p in list(getattr(ex, "_processes", {}).values() if getattr(ex, "_processes", None) else []):
        try:
            p.join(5)
        except Exception:
            pass


def pmap(fn, items, n, chunksize=1, ordered=True, label="workers", pickled=False):
    """fn(item) for every item in n forked processes (fn and the items reach the workers through the fork, nothing is
    pickled on the way in); the results in the order of items (ordered) or as they come. A dead or stalled worker
    pool is replaced by one of half the size for the items left; at 1 they run here. pickled: fn and the items can
    be pickled, so a system without fork (Windows) runs them in spawned processes instead of this one."""
    global _JOB
    items = list(items)
    fork = hasattr(os, "fork")
    if n <= 1 or len(items) < 2 or not (fork or pickled):
        for it in items:
            yield fn(it)
        return
    import multiprocessing as mp
    from collections import deque
    from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
    from concurrent.futures.process import BrokenProcessPool
    import time
    chunks = [list(range(i, min(i + chunksize, len(items)))) for i in range(0, len(items), chunksize)]
    todo = deque(range(len(chunks)))
    ready, nxt = {}, 0
    n = min(n, len(chunks))
    prev = _JOB
    _JOB = (fn, items)
    try:
        while todo:
            if n <= 1:
                for c in list(todo):
                    for i in chunks[c]:
                        ready[i] = fn(items[i])
                    todo.popleft()
                    while ordered and nxt in ready:
                        yield ready.pop(nxt)
                        nxt += 1
                    if not ordered:
                        for i in list(ready):
                            yield ready.pop(i)
                break
            sys.stdout.flush()
            sys.stderr.flush()
            ex = ProcessPoolExecutor(n, mp_context=mp.get_context("fork" if fork else "spawn"))
            running = {}
            broken = None
            t_last, cpu_last = time.time(), None
            try:
                while todo or running:
                    while todo and len(running) < 2 * n:
                        try:
                            f = ex.submit(_run_chunk, chunks[todo[0]]) if fork else ex.submit(
                                _run_pickled, fn, [(i, items[i]) for i in chunks[todo[0]]])
                        except BrokenProcessPool:
                            broken = "a worker process died: most likely out of memory"
                            break
                        running[f] = todo.popleft()
                    if broken:
                        break
                    done, _ = wait(list(running), timeout=30, return_when=FIRST_COMPLETED)
                    if not done:
                        cpu = _workers_cpu(ex)
                        if cpu is not None and (cpu_last is None or cpu < cpu_last or cpu - cpu_last >= 2.0):
                            # a rolling window: the clock restarts whenever the workers used 2 s of CPU, so a worker
                            # that computed for a while and then blocked is caught POOL_STALL s after it stopped
                            t_last, cpu_last = time.time(), cpu
                        if cpu is not None and time.time() - t_last > POOL_STALL:
                            broken = "no result and no CPU in the workers for %.0f s" % (time.time() - t_last)
                            break
                        continue
                    t_last, cpu_last = time.time(), _workers_cpu(ex)
                    for f in done:
                        c = running.pop(f)
                        try:
                            for i, r in f.result():
                                ready[i] = r
                        except BrokenProcessPool as e:
                            broken = "a worker process died (%s): most likely out of memory" % (str(e)[:120] or
                                                                                               "killed")
                            todo.appendleft(c)
                    if broken:
                        break
                    while ordered and nxt in ready:
                        yield ready.pop(nxt)
                        nxt += 1
                    if not ordered:
                        for i in list(ready):
                            yield ready.pop(i)
            finally:
                if broken or todo or running:
                    _kill(ex)
                else:
                    ex.shutdown(wait=True)
            if broken:
                for f, c in running.items():
                    todo.appendleft(c)
                todo = deque(sorted(set(todo)))
                n2 = max(1, n // 2)
                print("  %s: %s; the %d items left again with %d %s" % (
                    label, broken, sum(len(chunks[c]) for c in todo), n2,
                    "processes" if n2 > 1 else "process (this one)"), flush=True)
                n = n2
        while ordered and nxt in ready:
            yield ready.pop(nxt)
            nxt += 1
    finally:
        _JOB = prev


def imap(fn, items, state, n=None, chunksize=1):
    """fn(state, item) for every item, in the order of items; in n forked processes when n > 1 (pmap: a worker
    killed for memory does not hang the step)."""
    global STATE, _FN
    items = list(items)
    n = workers() if n is None else n
    STATE, _FN = state, fn
    try:
        if n <= 1 or len(items) < 2:
            for it in items:
                yield fn(state, it)
            return
        for r in pmap(_call, items, min(n, len(items)), chunksize, label="tile workers"):
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
