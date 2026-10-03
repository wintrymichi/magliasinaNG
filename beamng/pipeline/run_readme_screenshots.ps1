# README screenshots in the game (v2.6): writes the camera tour, runs the magliaso_readme extension,
# (all of them, or only -Views name1,name2) waits until it has finished and converts the shots to beamng/verifica/screenshots/<name>.jpg.
param([string[]]$Views = @(), [string]$Zip = "D:\beamng_magliaso\dist\magliaso_pura_v2.6.zip", [int]$TimeoutSec = 1800, [string]$Python = "D:\beamng_magliaso\venv\Scripts\python.exe")
$here = $PSScriptRoot
$game = "C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
$user = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
$out = Join-Path (Split-Path $here) "verifica\screenshots"
Push-Location $here; & $Python ingame_screenshots.py @Views; Pop-Location
# extension "magliaso_readme" is looked up as lua/ge/extensions/magliaso/readme.lua
$ext = Join-Path $user "lua\ge\extensions\magliaso"
New-Item -ItemType Directory -Force $ext | Out-Null
Copy-Item (Join-Path $here "bng_lua\magliaso_readme.lua") (Join-Path $ext "readme.lua") -Force
$shots = Join-Path $user "screenshots\magliaso_readme"
if (Test-Path $shots) { Remove-Item "$shots\*" -Force -Confirm:$false }
if (-not (Get-Process steam -ErrorAction SilentlyContinue)) {
    Start-Process "C:\Program Files (x86)\Steam\steam.exe" -ArgumentList "-silent"; Start-Sleep -Seconds 25
}
# the level as a mod in <user>/mods for this run only (the copy in mods/multiplayer is BeamMP's: it is
# not mounted outside a BeamMP session, and BeamMP deletes it when the game starts without it)
$mods = Join-Path $user "mods"
$tmpZip = Join-Path $mods (Split-Path $Zip -Leaf)
$dbBak = Join-Path $env:TEMP "magliaso_mods_db.json"
Copy-Item (Join-Path $mods "db.json") $dbBak -Force
$ownZip = -not (Test-Path $tmpZip)
if ($ownZip) { Copy-Item $Zip $tmpZip }
$t0 = Get-Date
Start-Process -FilePath (Join-Path $game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $game -ArgumentList "-level magliaso_pura -onLevelLoad_ext magliaso_readme"
while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
    Start-Sleep -Seconds 5
    if (Test-Path (Join-Path $shots "_done.txt")) { break }
    if (-not (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) -and ((Get-Date) - $t0).TotalSeconds -gt 90) { break }
}
Start-Sleep -Seconds 5
Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Start-Sleep -Seconds 3
if ($ownZip) { Remove-Item $tmpZip -Force -Confirm:$false }
Copy-Item $dbBak (Join-Path $mods "db.json") -Force
Select-String -Path (Join-Path $user "beamng.log") -Pattern "magliaso_readme|Level loaded in" | Select-Object -Last 20 | ForEach-Object { $_.Line }
# PNG -> 1600 px JPG, like the renders it replaces
& $Python -c "import glob, os, sys; from PIL import Image
for f in sorted(glob.glob(os.path.join(sys.argv[1], '*.png'))):
    im = Image.open(f).convert('RGB'); w, h = im.size
    if w > 1600: im = im.resize((1600, round(h * 1600 / w)), Image.LANCZOS)
    o = os.path.join(sys.argv[2], os.path.basename(f)[:-4] + '.jpg'); im.save(o, quality=88); print(o, im.size)" $shots $out
