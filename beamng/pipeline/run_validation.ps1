# Run the in-game camera tour (magliaso_validate extension) and wait until it has finished.
param([int]$TimeoutSec = 1800)
$game = "C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
$user = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
$ext = Join-Path $user "lua\ge\extensions"
New-Item -ItemType Directory -Force $ext | Out-Null
# extension "magliaso_validate" is looked up as lua/ge/extensions/magliaso/validate.lua
New-Item -ItemType Directory -Force (Join-Path $ext "magliaso") | Out-Null
Copy-Item "C:\Users\michi\streetview_strada_cantonale\pipeline\bng_lua\magliaso_validate.lua" (Join-Path $ext "magliaso\validate.lua") -Force
Remove-Item (Join-Path $ext "magliaso_validate.lua") -ErrorAction SilentlyContinue
$shots = Join-Path $user "screenshots\magliaso"
if (Test-Path $shots) { Remove-Item "$shots\*" -Force -Confirm:$false }
if (-not (Get-Process steam -ErrorAction SilentlyContinue)) {
    Start-Process "C:\Program Files (x86)\Steam\steam.exe" -ArgumentList "-silent"; Start-Sleep -Seconds 25
}
$t0 = Get-Date
Start-Process -FilePath (Join-Path $game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $game -ArgumentList "-level magliaso_pura -onLevelLoad_ext magliaso_validate"
while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
    Start-Sleep -Seconds 5
    if (Test-Path (Join-Path $shots "_done.txt")) { break }
    if (-not (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) -and ((Get-Date) - $t0).TotalSeconds -gt 90) { break }
}
Start-Sleep -Seconds 5
Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Copy-Item (Join-Path $user "beamng.log") "D:\beamng_magliaso\work\beamng_validate.log" -Force
"shots: " + (Get-ChildItem $shots -Filter *.png -ErrorAction SilentlyContinue).Count
Select-String -Path (Join-Path $user "beamng.log") -Pattern "magliaso_validate|Level loaded in" | Select-Object -Last 8 | ForEach-Object { $_.Line }
