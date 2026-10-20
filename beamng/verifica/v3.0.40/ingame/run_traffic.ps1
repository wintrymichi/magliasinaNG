# The traffic run of the v3.0.40 in-game test on Windows: the traffic thread's magliaso_traffic.lua (navgraph, signals,
# parking, traffic samples, state, frame time), 12 traffic cars and 30 parked for 10 minutes; memory sampled every 2 s.
# Copies <user>\magliaso_traffic\ (navgraph.json gzipped), the memory and the log lines to <user>\magliaso_v3040_out\traffic\.
#   powershell -ExecutionPolicy Bypass -File run_traffic.ps1
param([int]$TimeoutMin = 30,
      [string]$Game = "G:\SteamLibrary\steamapps\common\BeamNG.drive",
      [string]$User = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current")
$here = $PSScriptRoot
if (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) { throw "BeamNG is running: close it first" }
$out = Join-Path $User "magliaso_v3040_out\traffic"
New-Item -ItemType Directory -Force $out | Out-Null
$extFile = Join-Path $User "lua\ge\extensions\magliaso_traffic.lua"
New-Item -ItemType Directory -Force (Split-Path $extFile) | Out-Null
Copy-Item (Join-Path $here "magliaso_traffic.lua") $extFile -Force
$work = Join-Path $User "magliaso_traffic"
if (Test-Path $work) { Remove-Item $work -Recurse -Force -Confirm:$false }
New-Item -ItemType Directory -Force $work | Out-Null
'{"traffic": 12, "parked": 30, "duration": 600, "every": 2, "quit": true}' | Set-Content (Join-Path $work "options.json")
$log = Join-Path $User "beamng.log"
$csv = Join-Path $out "memory.csv"
"seconds,working_set_mb,private_mb" | Set-Content $csv
$t0 = Get-Date
$p = Start-Process -FilePath (Join-Path $Game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $Game `
     -ArgumentList "-level magliaso_pura/main.level.json -onLevelLoad_ext magliaso_traffic" -PassThru
while (((Get-Date) - $t0).TotalMinutes -lt $TimeoutMin) {
    Start-Sleep -Seconds 2
    $g = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
    if (-not $g) { break }
    "{0},{1},{2}" -f [math]::Round(((Get-Date) - $t0).TotalSeconds), [math]::Round($g.WorkingSet64 / 1MB),
        [math]::Round($g.PrivateMemorySize64 / 1MB) | Add-Content $csv
    if (Test-Path (Join-Path $work "done.txt")) { Start-Sleep -Seconds 20; break }
}
if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $p.Id -Force -Confirm:$false; Start-Sleep 5 }
Copy-Item (Join-Path $work "*") $out -Recurse -Force
$nav = Join-Path $out "navgraph.json"
if (Test-Path $nav) {
    $in = [IO.File]::OpenRead($nav); $o = [IO.File]::Create("$nav.gz")
    $gz = New-Object IO.Compression.GZipStream($o, [IO.Compression.CompressionMode]::Compress)
    $in.CopyTo($gz); $gz.Close(); $in.Close(); Remove-Item $nav
}
Copy-Item $log (Join-Path $out "beamng.log") -Force
Select-String -Path $log -Pattern "magliaso_traffic|traffic|parking|multiSpawn|trafficSignals|signal controller|map\.lua|navgraph|\[E\]|\[W\]|\|E\||\|W\||Level loaded in" |
    ForEach-Object { $_.Line } | Set-Content (Join-Path $out "log_lines.txt")
Remove-Item $extFile -Force -Confirm:$false
Remove-Item $work -Recurse -Force -Confirm:$false
Get-ChildItem $out | Select-Object Name, Length
