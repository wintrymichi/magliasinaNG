# The in-game check of the unpaved tracks (network_mesh.unpaved_step, v2.7) on one level zip: installs it alone in
# <user>/mods (the other magliaso_pura zips go to <user>/mods_aside and come back at the end), with the road
# shapes converted again (their cache in <user>/temp is moved aside and put back), runs the
# magliaso_unpaved extension on the tour of unpaved_tour.py and converts the shots to
# beamng/verifica/v2.7/unpaved/<tag>_<site>_<view>.jpg; the drives go to <tag>_drive.json.
#   run_unpaved_screenshots.ps1 -Zip <zip> -Tag before|after
param([Parameter(Mandatory)][string]$Zip, [Parameter(Mandatory)][string]$Tag, [int]$TimeoutSec = 1800,
      [string]$Python = "D:\beamng_magliaso\venv\Scripts\python.exe")
$here = $PSScriptRoot
$game = "C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
$user = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
$out = Join-Path (Split-Path $here) "verifica\v2.7\unpaved"
if (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) { throw "BeamNG.drive is already running" }
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $here; & $Python unpaved_tour.py views $Zip $Tag; Pop-Location
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
$cache = Join-Path $user "temp\levels\magliaso_pura\art\shapes\roads"
$stash = "$cache.stash_unpaved"
if ((Test-Path $cache) -and -not (Test-Path $stash)) { Move-Item $cache $stash }
elseif (Test-Path $cache) { Remove-Item $cache -Recurse -Force -Confirm:$false }
try {
    $log = Join-Path $user "beamng.log"
    $t0 = Get-Date
    Start-Process -FilePath (Join-Path $game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $game -ArgumentList "-level magliaso_pura -onLevelLoad_ext magliaso_unpaved"
    while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
        Start-Sleep -Seconds 5
        if (Test-Path (Join-Path $shots "_done.txt")) { break }
        if (-not (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) -and ((Get-Date) - $t0).TotalSeconds -gt 90) { break }
    }
    "run: $([int]((Get-Date) - $t0).TotalSeconds) s"
    Start-Sleep -Seconds 5
    Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
    Start-Sleep -Seconds 3
    Select-String -Path $log -Pattern "magliaso_unpaved|Level loaded in" | ForEach-Object { $_.Line } | Select-Object -Last 60
} finally {
    Remove-Item $dst -Force -Confirm:$false -ErrorAction SilentlyContinue
    $moved | ForEach-Object { Move-Item (Join-Path $aside $_.Name) $mods -Force; "back: $($_.Name)" }
    if (Test-Path $stash) {
        if (Test-Path $cache) { Remove-Item $cache -Recurse -Force -Confirm:$false }
        Move-Item $stash $cache
    }
}
if (Test-Path (Join-Path $shots "_drive.json")) { Copy-Item (Join-Path $shots "_drive.json") (Join-Path $out "$($Tag)_drive.json") -Force }
& $Python -c "import glob, os, sys; from PIL import Image
for f in sorted(glob.glob(os.path.join(sys.argv[1], '*.png'))):
    im = Image.open(f).convert('RGB'); w, h = im.size
    if w > 1600: im = im.resize((1600, round(h * 1600 / w)), Image.LANCZOS)
    o = os.path.join(sys.argv[2], os.path.basename(f)[:-4] + '.jpg'); im.save(o, quality=85); print(o, im.size)" $shots $out
