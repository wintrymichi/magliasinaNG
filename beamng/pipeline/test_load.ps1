# Load-test the level in BeamNG.drive: start (via Steam), wait for the level to load,
# grab a screenshot, collect errors from beamng.log, close the game.
param(
    [string]$Level = "magliaso_pura",
    [int]$TimeoutSec = 420,
    [string]$Shot = "D:\beamng_magliaso\work\ingame_test.png",
    [int]$ExtraWaitSec = 25
)
$game = "C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
$user = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
$log = Join-Path $user "beamng.log"

if (-not (Get-Process steam -ErrorAction SilentlyContinue)) {
    Start-Process "C:\Program Files (x86)\Steam\steam.exe" -ArgumentList "-silent"
    Start-Sleep -Seconds 25
}
$t0 = Get-Date
Start-Process -FilePath (Join-Path $game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $game -ArgumentList "-level $Level"
$loaded = $false
while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
    Start-Sleep -Seconds 5
    if ((Test-Path $log) -and ((Get-Item $log).LastWriteTime -gt $t0)) {
        $txt = Get-Content $log -Raw -ErrorAction SilentlyContinue
        if ($txt -match "Level loaded in") { $loaded = $true; break }
        if ($txt -match "gameStartupError|Fatal|fatal error") { break }
    }
    if (-not (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) -and ((Get-Date) - $t0).TotalSeconds -gt 60) { break }
}
if ($loaded) { Start-Sleep -Seconds $ExtraWaitSec }
# screenshot of the primary screen
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$bmp.Save($Shot, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Start-Sleep -Seconds 3
"LOADED=$loaded"
Copy-Item $log "D:\beamng_magliaso\work\beamng_test.log" -Force
Select-String -Path $log -Pattern "Level loading|Level loaded|LoadingManager\| Loaded|Static Collision|\|E\||\|W\|.*(level|terrain|material|shape|dae|collada|magliaso)" | Select-Object -Last 80 | ForEach-Object { $_.Line }
