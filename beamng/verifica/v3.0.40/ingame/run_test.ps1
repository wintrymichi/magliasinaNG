# One run of the v3.0.40 in-game test on Windows (magliaso_v3040.lua): installs the extension and the plan, starts
# the game into magliaso_pura with it, samples the game's memory every 2 s while it runs, waits until the plan is done
# (the extension quits the game) and copies what it wrote to <user>\magliaso_v3040_out\<Tag>\.
#   powershell -ExecutionPolicy Bypass -File run_test.ps1 -Tag v3040 -Plan plan_v3040.json
# The level zip in mods\ is whatever is installed: swap it before the run to measure another version.
param([Parameter(Mandatory = $true)][string]$Tag, [Parameter(Mandatory = $true)][string]$Plan,
      [int]$TimeoutMin = 90,
      [string]$Game = "G:\SteamLibrary\steamapps\common\BeamNG.drive",
      [string]$User = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current")
$here = $PSScriptRoot
if (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) { throw "BeamNG is running: close it first" }
$out = Join-Path $User "magliaso_v3040_out\$Tag"
New-Item -ItemType Directory -Force $out | Out-Null
$ext = Join-Path $User "lua\ge\extensions\magliaso"
New-Item -ItemType Directory -Force $ext | Out-Null
Copy-Item (Join-Path $here "magliaso_v3040.lua") (Join-Path $ext "v3040.lua") -Force
$work = Join-Path $User "magliaso_v3040"
if (Test-Path $work) { Remove-Item $work -Recurse -Force -Confirm:$false }
New-Item -ItemType Directory -Force (Join-Path $work "shots") | Out-Null
Copy-Item (Join-Path $here $Plan) (Join-Path $work "plan.json") -Force
$log = Join-Path $User "beamng.log"

$csv = Join-Path $out "memory.csv"
"seconds,working_set_mb,private_mb,gpu_dedicated_mb,gpu_used_total_mb" | Set-Content $csv
$nvsmi = (Get-Command nvidia-smi -ErrorAction SilentlyContinue).Source
$gpu0 = if ($nvsmi) { [int](& $nvsmi --query-gpu=memory.used --format=csv,noheader,nounits) } else { -1 }
"gpu memory used before the start: $gpu0 MB" | Set-Content (Join-Path $out "gpu_before.txt")

$t0 = Get-Date
$p = Start-Process -FilePath (Join-Path $Game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $Game `
     -ArgumentList "-level magliaso_pura/main.level.json -onLevelLoad_ext magliaso_v3040" -PassThru
while (((Get-Date) - $t0).TotalMinutes -lt $TimeoutMin) {
    Start-Sleep -Seconds 2
    $g = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
    if (-not $g) { break }
    $ded = -1
    try {
        $s = (Get-Counter "\GPU Process Memory(pid_$($p.Id)_*)\Dedicated Usage" -ErrorAction Stop).CounterSamples
        $ded = [math]::Round(($s | Measure-Object CookedValue -Sum).Sum / 1MB)
    } catch {}
    $tot = if ($nvsmi) { [int](& $nvsmi --query-gpu=memory.used --format=csv,noheader,nounits) } else { -1 }
    "{0},{1},{2},{3},{4}" -f [math]::Round(((Get-Date) - $t0).TotalSeconds), [math]::Round($g.WorkingSet64 / 1MB),
        [math]::Round($g.PrivateMemorySize64 / 1MB), $ded, $tot | Add-Content $csv
    if (Test-Path (Join-Path $work "done.txt")) { Start-Sleep -Seconds 20; break }
}
if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $p.Id -Force -Confirm:$false; Start-Sleep 5 }
"run took {0:N0} s" -f ((Get-Date) - $t0).TotalSeconds | Set-Content (Join-Path $out "run.txt")
Copy-Item (Join-Path $work "*") $out -Recurse -Force
Copy-Item $log (Join-Path $out "beamng.log") -Force
$m = Import-Csv $csv
function Peak($col) { ($m | ForEach-Object { [int]$_.$col } | Measure-Object -Maximum).Maximum }
if ($m) {
    "peak working set {0} MB, peak private {1} MB, peak GPU dedicated {2} MB, peak GPU used (all) {3} MB" -f `
        (Peak "working_set_mb"), (Peak "private_mb"), (Peak "gpu_dedicated_mb"), (Peak "gpu_used_total_mb") |
        Tee-Object (Join-Path $out "memory_peak.txt")
}
Select-String -Path $log -Pattern "Level loaded in|magliaso_v3040|Failed to load|NO-MATERIAL|Direct3D|resolution" |
    Select-Object -Last 200 | ForEach-Object { $_.Line } | Set-Content (Join-Path $out "log_lines.txt")
Get-Content (Join-Path $out "log_lines.txt") | Select-Object -Last 40
