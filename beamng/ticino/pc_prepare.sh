#!/usr/bin/env bash
# Ticino a blocchi, phase 0/1 test: prepare the test mod on the Linux PC, everything on the big data disk.
#   bash pc_prepare.sh /mnt/<6TB disk>
# Downloads the released v3.1.1 zip (public), unpacks it, cuts it into blocks (blocks.py, ~1-2 min), checks the blocks
# against the source terrain and packs <disk>/ticino/ticino_test.zip. It does not touch the game or its user folder:
# installing the zip in mods/ is a step of the test itself (README.md).
set -euo pipefail
DISK=${1:?usage: pc_prepare.sh <data disk>}
HERE=$(cd "$(dirname "$0")" && pwd)
W="$DISK/ticino"
mkdir -p "$W/src" "$W/out"
ZIP="$W/magliaso_pura_v3.1.1.zip"
if [ ! -s "$ZIP" ]; then
  curl -L --fail -o "$ZIP.part" https://github.com/wintrymichi/magliasinaNG/releases/download/v3.1.1/magliaso_pura_v3.1.1.zip
  mv "$ZIP.part" "$ZIP"
fi
if [ ! -f "$W/src/levels/magliaso_pura/theTerrain.ter" ]; then
  unzip -q -o "$ZIP" -d "$W/src"
fi
python3 "$HERE/blocks.py" --zone "$HERE/zones/malcantone.json" --src "$W/src" --out "$W/out"
python3 "$HERE/tests/check_blocks.py" --zone "$HERE/zones/malcantone.json" --src "$W/src" --out "$W/out" --n 6
if command -v luajit >/dev/null; then python3 "$HERE/tests/test_lua.py" --out "$W/out"; fi
python3 "$HERE/package.py" --out "$W/out" --zip "$W/ticino_test.zip"
echo "ready: $W/ticino_test.zip"
