"""Put the baked imposters of the far trees into a built zip of the level (v3.0.40), without building it again.

far_trees.prebaked does this in the build; this is for a zip built before it (the nightly #2 of v3.0.40): beside
every far model of the zip whose DAE is the one dati/far_imposters was baked from, its .dae.asset.json and its
two imposter pictures, dated now (newer than the shape, so the game keeps them). A zip with them already gets
them again.

Run: python patch_far_imposters.py <level zip>
"""
import hashlib, json, os, shutil, sys, tempfile, time, zipfile
import far_trees
from config import LEVEL_NAME


def patch(path):
    baked = json.load(open(os.path.join(far_trees.IMPOSTERS, "baked.json")))["dae_md5"]
    d = f"levels/{LEVEL_NAME}/art/shapes/trees/"
    now = time.localtime(time.time() + 60)[:6]
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        add = {}
        for n in far_trees.names():
            dae = d + n + ".dae"
            if dae not in names:
                print("not in the zip:", dae)
                continue
            if hashlib.md5(z.read(dae)).hexdigest() != baked.get(n):
                print("other model than the baked one, left to the game:", dae)
                continue
            add[dae + ".asset.json"] = json.dumps(far_trees.asset()).encode()
            for suffix in (".imposter.dds", ".imposter_normals.dds"):
                add[dae + suffix] = open(os.path.join(far_trees.IMPOSTERS, n + ".dae" + suffix), "rb").read()
        again = names & set(add)
    if again:                                   # rewrite without the old copies
        fd, tmp = tempfile.mkstemp(suffix=".zip", dir=os.path.dirname(os.path.abspath(path)))
        os.close(fd)
        with zipfile.ZipFile(path) as zi, zipfile.ZipFile(tmp, "w") as zo:
            for i in zi.infolist():
                if i.filename not in again:
                    with zi.open(i) as src, zo.open(i, "w") as dst:
                        shutil.copyfileobj(src, dst, 1 << 24)
        os.replace(tmp, path)
    with zipfile.ZipFile(path, "a") as z:
        for name, data in sorted(add.items()):
            ctype = zipfile.ZIP_STORED if name.endswith(".dds") else zipfile.ZIP_DEFLATED
            z.writestr(zipfile.ZipInfo(name, now), data, compress_type=ctype)
    print("far tree imposters: %d files added beside %d of %d far models of %s"
          % (len(add), sum(n.endswith(".asset.json") for n in add), len(far_trees.names()), path), flush=True)
    return len(add)


if __name__ == "__main__":
    patch(sys.argv[1])
