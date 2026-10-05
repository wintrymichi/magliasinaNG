# Road-sign screenshots in the game (v2.7): installs the v2.7 zip in <user>/mods (an older magliaso_pura zip
# in <user>/mods is moved to <user>/mods_aside: two zips of the same level would mix their files), runs the
# magliaso_signs extension on the tour written by signs_screenshots.py, waits until it has finished and
# converts the shots to beamng/verifica/screenshots/signs_v2.7/<name>.jpg. The v2.7 zip stays installed.
param([string]$Zip = "D:\beamng_magliaso\dist\magliaso_pura_v2.7.zip", [int]$TimeoutSec = 1800,
      [string]$Python = "D:\beamng_magliaso\venv\Scripts\python.exe")
$here = $PSScriptRoot
$game = "C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
$user = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
$out = Join-Path (Split-Path $here) "verifica\screenshots\signs_v2.7"
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $here; & $Python signs_screenshots.py; Pop-Location
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
$dst = Join-Path $mods (Split-Path $Zip -Leaf)
if (-not (Test-Path $dst) -or (Get-Item $dst).Length -ne (Get-Item $Zip).Length -or
    (Get-Item $dst).LastWriteTime -lt (Get-Item $Zip).LastWriteTime) { Copy-Item $Zip $dst -Force }
$log = Join-Path $user "beamng.log"
$t0 = Get-Date
Start-Process -FilePath (Join-Path $game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $game -ArgumentList "-level magliaso_pura -onLevelLoad_ext magliaso_signs"
while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
    Start-Sleep -Seconds 5
    if (Test-Path (Join-Path $shots "_done.txt")) { break }
    if (-not (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) -and ((Get-Date) - $t0).TotalSeconds -gt 90) { break }
}
"run: $([int]((Get-Date) - $t0).TotalSeconds) s"
Start-Sleep -Seconds 5
Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Start-Sleep -Seconds 3
Select-String -Path $log -Pattern "magliaso_signs|Level loaded in|props_signs|signs_ch|mp_ch_" | ForEach-Object { $_.Line } | Select-Object -Last 80
& $Python -c "import glob, os, sys; from PIL import Image
for f in sorted(glob.glob(os.path.join(sys.argv[1], '*.png'))):
    im = Image.open(f).convert('RGB'); w, h = im.size
    if w > 1600: im = im.resize((1600, round(h * 1600 / w)), Image.LANCZOS)
    o = os.path.join(sys.argv[2], os.path.basename(f)[:-4] + '.jpg'); im.save(o, quality=85); print(o, im.size)" $shots $out
