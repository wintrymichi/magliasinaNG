# The in-game check of the undergrowth and the darker forest floor (understory.understory_step, v2.8) on one level
# zip: installs it alone in <user>/mods (the other magliaso_pura zips go to <user>/mods_aside and come back at
# the end), runs the views of understory_tour.py with the magliaso_unpaved extension (with the frame rate of
# every view), converts the shots to beamng/verifica/v2.8/understory/game/<tag>_<site>.jpg and writes the
# frame rates, the load time and the game's peak memory to <tag>_fps.json there.
#   run_understory_screenshots.ps1 -Zip <zip> -Tag before|after
param([Parameter(Mandatory)][string]$Zip, [Parameter(Mandatory)][string]$Tag, [int]$TimeoutSec = 1800,
      [string]$Python = "D:\beamng_magliaso\venv\Scripts\python.exe")
$here = $PSScriptRoot
$game = "C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
$user = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
$out = Join-Path (Split-Path $here) "verifica\v2.8\understory\game"
if (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) { throw "BeamNG.drive is already running" }
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $here; & $Python understory_tour.py views $Zip $Tag; Pop-Location
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
try {
    $log = Join-Path $user "beamng.log"
    $t0 = Get-Date
    Start-Process -FilePath (Join-Path $game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $game -ArgumentList "-level magliaso_pura -onLevelLoad_ext magliaso_unpaved"
    $peak = 0
    while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
        Start-Sleep -Seconds 5
        $p = Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue
        if ($p) { $peak = [math]::Max($peak, $p.PeakWorkingSet64) }
        if (Test-Path (Join-Path $shots "_done.txt")) { break }
        if (-not (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) -and ((Get-Date) - $t0).TotalSeconds -gt 90) { break }
    }
    "run: $([int]((Get-Date) - $t0).TotalSeconds) s"
    Start-Sleep -Seconds 5
    Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
    Start-Sleep -Seconds 3
    $lines = @(Select-String -Path $log -Pattern "magliaso_unpaved|Level loaded in" | ForEach-Object { $_.Line })
    $lines | Select-Object -Last 60
    $load = ($lines | Select-String -Pattern "Level loaded in" | Select-Object -Last 1)
    $fps = @{}
    if (Test-Path (Join-Path $shots "_drive.json")) { (Get-Content (Join-Path $shots "_drive.json") -Raw | ConvertFrom-Json) | ForEach-Object { if ($_.fps) { $fps[$_.name] = [math]::Round($_.fps, 1) } } }
    @{zip = (Split-Path $Zip -Leaf); peak_memory_gb = [math]::Round($peak / 1GB, 2); load = "$load"; fps = $fps} |
        ConvertTo-Json -Depth 3 | Set-Content (Join-Path $out "$($Tag)_fps.json")
    "peak memory: $([math]::Round($peak / 1GB, 2)) GB"
} finally {
    Remove-Item $dst -Force -Confirm:$false -ErrorAction SilentlyContinue
    $moved | ForEach-Object { Move-Item (Join-Path $aside $_.Name) $mods -Force; "back: $($_.Name)" }
}
& $Python -c "import glob, os, sys; from PIL import Image
for f in sorted(glob.glob(os.path.join(sys.argv[1], '*.png'))):
    im = Image.open(f).convert('RGB'); w, h = im.size
    if w > 1600: im = im.resize((1600, round(h * 1600 / w)), Image.LANCZOS)
    o = os.path.join(sys.argv[2], os.path.basename(f)[:-4] + '.jpg'); im.save(o, quality=85); print(o, im.size)" $shots $out
