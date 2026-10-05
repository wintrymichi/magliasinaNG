# The final v2.7 check in the game (beamng/verifica/v2.7/final_test_plan.md, steps 3-4): installs the zip in
# <user>/mods in place of the v2.7 there (other magliaso_pura zips go to <user>/mods_aside), deletes the game's
# converted copy of the level (<user>/temp/levels/magliaso_pura) so shapes and imposters are converted again,
# runs the magliaso_signs extension on the tour of final_screenshots.py and writes the shots as 1920x1080 jpg
# to beamng/verifica/screenshots/v2.7/<name>.jpg and the load time, fps per view and log errors to test.json.
param([string]$Zip = "D:\beamng_magliaso\dist\magliaso_pura_v2.7.zip", [int]$TimeoutSec = 2400, [switch]$KeepCache,
      [string]$Python = "D:\beamng_magliaso\venv\Scripts\python.exe")
$here = $PSScriptRoot
$game = "C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
$user = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
$out = Join-Path (Split-Path $here) "verifica\screenshots\v2.7"
if (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) { throw "BeamNG.drive is already running" }
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $here; & $Python final_screenshots.py $Zip; Pop-Location
$ext = Join-Path $user "lua\ge\extensions\magliaso"
New-Item -ItemType Directory -Force $ext | Out-Null
Copy-Item (Join-Path $here "bng_lua\magliaso_signs.lua") (Join-Path $ext "signs.lua") -Force
$shots = Join-Path $user "screenshots\magliaso_signs"
if (Test-Path $shots) { Remove-Item "$shots\*" -Force -Confirm:$false }
if (-not (Get-Process steam -ErrorAction SilentlyContinue)) {
    Start-Process "C:\Program Files (x86)\Steam\steam.exe" -ArgumentList "-silent"; Start-Sleep -Seconds 25
}
$mods = Join-Path $user "mods"
$aside = Join-Path $user "mods_aside"
New-Item -ItemType Directory -Force $aside | Out-Null
Get-ChildItem $mods -Filter "magliaso_pura*.zip" | Where-Object { $_.Name -ne (Split-Path $Zip -Leaf) } |
    ForEach-Object { Move-Item $_.FullName $aside -Force; "moved aside: $($_.Name)" }
Copy-Item $Zip (Join-Path $mods (Split-Path $Zip -Leaf)) -Force
$cache = Join-Path $user "temp\levels\magliaso_pura"
if ((Test-Path $cache) -and -not $KeepCache) { Remove-Item $cache -Recurse -Force -Confirm:$false; "deleted $cache" }
$log = Join-Path $user "beamng.log"
$t0 = Get-Date
Start-Process -FilePath (Join-Path $game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $game -ArgumentList "-level magliaso_pura -onLevelLoad_ext magliaso_signs"
# the game in front: behind other windows it holds 30 fps
Add-Type -AssemblyName Microsoft.VisualBasic
while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
    Start-Sleep -Seconds 5
    $p = Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { try { [Microsoft.VisualBasic.Interaction]::AppActivate($p.Id) } catch {} }
    if (Test-Path (Join-Path $shots "_done.txt")) { break }
    if (-not (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) -and ((Get-Date) - $t0).TotalSeconds -gt 90) { break }
}
$run = [int]((Get-Date) - $t0).TotalSeconds
"run: $run s"
Start-Sleep -Seconds 5
Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Start-Sleep -Seconds 3
Copy-Item $log (Join-Path $env:TEMP "magliaso_final_beamng.log") -Force
& $Python -c "import glob, hashlib, json, os, re, sys
from PIL import Image
shots, out, log, zp, run, cache = sys.argv[1:7]
files = []
for f in sorted(glob.glob(os.path.join(shots, '[!_]*.png'))):
    im = Image.open(f).convert('RGB').resize((1920, 1080), Image.LANCZOS)
    o = os.path.join(out, os.path.basename(f)[:-4] + '.jpg')
    for q in (88, 84, 80, 75, 70, 65, 60, 55):
        im.save(o, quality=q)
        if os.path.getsize(o) < 400000: break
    files.append(os.path.basename(o)); print(o, os.path.getsize(o) // 1024, 'KB q', q)
L = open(log, encoding='utf-8', errors='replace').read().splitlines()
load = next((l.split('|')[-1].strip() for l in L if 'Level loaded in' in l), None)
fps = {m.group(1): float(m.group(2)) for l in L for m in [re.search(r'magliaso_signs\| fps (\S+) ([\d.]+)', l)] if m}
err = sorted({re.sub(r'^\s*[\d.]+\|', '', l)[:220] for l in L if '|E|' in l and 'screenshot' not in l})
md5 = hashlib.md5(open(zp, 'rb').read()).hexdigest()
json.dump({'zip': os.path.basename(zp), 'zip_bytes': os.path.getsize(zp), 'zip_md5': md5, 'level_load': load,
           'run_s': int(run), 'cache': cache, 'fps': fps, 'log_errors': err,
           'screenshots': files}, open(os.path.join(out, 'test.json'), 'w'), indent=1)
print(load); print(len(err), 'log errors'); print(fps)" $shots $out (Join-Path $env:TEMP "magliaso_final_beamng.log") $Zip $run $(if ($KeepCache) { "warm" } else { "cold (temp/levels/magliaso_pura deleted)" })
