"""Put the grass of groundcover.py into a built level zip (v2.6), without rebuilding the level.

The GroundCover objects of the vegetation group are replaced with groundcover.objects(), the
materials of art/shapes/groundcover with groundcover.materials(); the textures drawn by the
v2.4-v2.5 pipeline (gc_atlas_*) are left out, and the level's README.md is the pipeline's
README_livello.md. Everything else is copied as it is (same entries,
same dates: the game keeps its converted shapes).

Usage: python patch_groundcover.py <in.zip> <out.zip>
"""
import json, os, re, sys, zipfile
import groundcover

LEVEL_README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README_livello.md")


def main(src, dst):
    zi = zipfile.ZipFile(src)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for i in zi.infolist():
            n = i.filename
            if "/art/shapes/groundcover/gc_atlas" in n:
                continue
            data = zi.read(i)
            if re.fullmatch(r"levels/[^/]+/README\.md", n):
                data = open(LEVEL_README, "rb").read()
            elif n.endswith("/art/shapes/groundcover/main.materials.json"):
                data = json.dumps({m["name"]: m for m in groundcover.materials()}, indent=1).encode("utf-8")
            elif n.endswith("level_objects/vegetation/items.level.json"):
                objs = [json.loads(l) for l in data.decode("utf-8").splitlines() if l.strip()]
                parent = next((o["__parent"] for o in objs if o.get("class") == "GroundCover"), "vegetation")
                objs = [o for o in objs if o.get("class") != "GroundCover"]
                for o in groundcover.objects():
                    o["__parent"] = parent
                    objs.append(o)
                data = ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")
            zo.writestr(i, data, compress_type=i.compress_type)
    print(dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
