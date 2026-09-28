"""Seed WORK with the light results kept in the repository (../dati) when they are missing.

The level build reads the photo-derived results (poses, road profile, markings, guardrails,
lamps, terrain colours ...) from WORK, where the Street View steps write them. On a machine
without the panoramas (a cloud build of v2.0) they come from ../dati, which holds copies of
them. Existing files in WORK are never overwritten.
"""
import os, shutil
from config import WORK

DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")


def main():
    n = 0
    for f in sorted(os.listdir(DATI)):
        dst = os.path.join(WORK, f)
        if not os.path.exists(dst):
            shutil.copy(os.path.join(DATI, f), dst)
            n += 1
    print(n, "files copied from dati to", WORK)


if __name__ == "__main__":
    main()
