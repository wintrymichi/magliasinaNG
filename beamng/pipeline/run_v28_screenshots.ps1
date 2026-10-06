# The in-game test of the whole v2.8 zip before its release (beamng/verifica/v2.8/final_test_plan.md): installs it
# alone in <user>/mods (the other magliaso_pura zips go to <user>/mods_aside and come back at the end), deletes the
# game's converted copy of the level (<user>/temp/levels/magliaso_pura, unless -KeepCache) so that the shapes and
# imposters are converted again, runs the views of the nine v2.8 checks (v28_tour.py) with the magliaso_unpaved
# extension, converts the shots to beamng/verifica/screenshots/v2.8/<topic>_<tag>_<site>.jpg and writes the zip's
# MD5, the load time, the frame rate of every view, the game's peak memory and the level errors of the log to
# test_<tag>.json there. The same views on the v2.7 zip (-Tag v27) give the frame rates and memory to compare.
#   run_v28_screenshots.ps1 -Zip D:\beamng_magliaso\dist\magliaso_pura_v2.8.zip [-Tag v28]
param([Parameter(Mandatory)][string]$Zip, [string]$Tag = "v28", [int]$TimeoutSec = 3600, [switch]$KeepCache,
      [string]$Python = "D:\beamng_magliaso\venv\Scripts\python.exe")
$here = $PSScriptRoot
$game = "C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
$user = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
$out = Join-Path (Split-Path $here) "verifica\screenshots\v2.8"
if (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) { throw "BeamNG.drive is already running" }
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $here; & $Python v28_tour.py views $Zip $Tag; Pop-Location
$ext = Join-Path $user "lua\ge\extensions\magliaso"
New-Item -ItemType Directory -Force $ext | Out-Null
Copy-Item (Join-Path $here "bng_lua\magliaso_unpaved.lua") (Join-Path $ext "unpaved.lua") -Force
$shots = Join-Path $user "screenshots\magliaso_unpaved"
if (Test-Path $shots) { Remove-Item "$shots\*" -Force -Confirm:$false }
if (-not (Get-Process steam -ErrorAction SilentlyContinue)) {
    Start-Process "C:\Program Files (x86)\Steam\steam.exe" -ArgumentList "-silent"; Start-Sleep -Seconds 25
}
$mods = Join-Path $user "mods"
$aside = Join-Path $user "mods_aside"
New-Item -ItemType Directory -Force $aside | Out-Null
$moved = @(Get-ChildItem $mods -Filter "magliaso_pura*.zip" | Where-Object { $_.Name -ne (Split-Path $Zip -Leaf) })
$moved | ForEach-Object { Move-Item $_.FullName $aside -Force; "moved aside: $($_.Name)" }
$dst = Join-Path $mods (Split-Path $Zip -Leaf)
Copy-Item $Zip $dst -Force
$cache = Join-Path $user "temp\levels\magliaso_pura"
if ((Test-Path $cache) -and -not $KeepCache) { Remove-Item $cache -Recurse -Force -Confirm:$false; "deleted $cache" }
try {
    $log = Join-Path $user "beamng.log"
    $t0 = Get-Date
    Start-Process -FilePath (Join-Path $game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $game -ArgumentList "-level magliaso_pura -onLevelLoad_ext magliaso_unpaved"
    # the game in front: behind other windows it holds 30 fps
    Add-Type -AssemblyName Microsoft.VisualBasic
    $peak = 0
    while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
        Start-Sleep -Seconds 5
        $p = Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue
        if ($p) { $peak = [math]::Max($peak, ($p | Measure-Object PeakWorkingSet64 -Maximum).Maximum) }
        $w = $p | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
        if ($w) { try { [Microsoft.VisualBasic.Interaction]::AppActivate($w.Id) } catch {} }
        if (Test-Path (Join-Path $shots "_done.txt")) { break }
        if (-not $p -and ((Get-Date) - $t0).TotalSeconds -gt 90) { break }
    }
    $run = [int]((Get-Date) - $t0).TotalSeconds
    "run: $run s, peak memory: $([math]::Round($peak / 1GB, 2)) GB"
    Start-Sleep -Seconds 5
    Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
    Start-Sleep -Seconds 3
    Copy-Item $log (Join-Path $env:TEMP "magliaso_v28_beamng.log") -Force
} finally {
    Remove-Item $dst -Force -Confirm:$false -ErrorAction SilentlyContinue
    $moved | ForEach-Object { Move-Item (Join-Path $aside $_.Name) $mods -Force; "back: $($_.Name)" }
}
& $Python -c "import glob, hashlib, json, os, re, sys
from PIL import Image
shots, out, log, zp, run, peak, cache, tag = sys.argv[1:9]
files = []
for f in sorted(glob.glob(os.path.join(shots, '[!_]*.png'))):
    im = Image.open(f).convert('RGB'); w, h = im.size
    if w > 1600: im = im.resize((1600, round(h * 1600 / w)), Image.LANCZOS)
    o = os.path.join(out, os.path.basename(f)[:-4] + '.jpg'); im.save(o, quality=85); files.append(os.path.basename(o))
L = open(log, encoding='utf-8', errors='replace').read().splitlines()
load = next((l.split('|')[-1].strip() for l in L if 'Level loaded in' in l), None)
fps = {}
dj = os.path.join(shots, '_drive.json')
if os.path.exists(dj):
    fps = {r['name']: round(r['fps'], 1) for r in json.load(open(dj)) if r.get('fps')}
err = sorted({re.sub(r'^\s*[\d.]+\|', '', l)[:220] for l in L if '|E|' in l and 'screenshot' not in l})
h = hashlib.md5()
with open(zp, 'rb') as fh:
    for b in iter(lambda: fh.read(1 << 20), b''): h.update(b)
json.dump({'zip': os.path.basename(zp), 'zip_bytes': os.path.getsize(zp), 'zip_md5': h.hexdigest(), 'level_load': load,
           'run_s': int(run), 'peak_memory_gb': round(float(peak) / 2**30, 2), 'cache': cache, 'fps': fps,
           'log_errors': err, 'screenshots': files}, open(os.path.join(out, f'test_{tag}.json'), 'w'), indent=1)
print(load); print(len(files), 'screenshots,', len(err), 'log errors'); print(fps)" $shots $out (Join-Path $env:TEMP "magliaso_v28_beamng.log") $Zip $run $peak $(if ($KeepCache) { "warm" } else { "cold (temp/levels/magliaso_pura deleted)" }) $Tag
