# One run of the Ticino phase 0 in-game test on Windows (autotest.lua): installs the test extension, starts the game
# into a level with it, samples the game's memory every 2 s, waits until the test is done (the extension quits the
# game), copies what it wrote to -Out and removes the test extension again. Run it once with -Level ticino (the test
# mod ticino_test.zip in mods\) and once with -Level magliaso_pura (v3.1.1, for the comparison). route.json
# (make_route.py) is the drive when the level has no AI road graph.
#   powershell -ExecutionPolicy Bypass -File run_test.ps1 -Level ticino -Out E:\ticino\results\ticino
param([Parameter(Mandatory = $true)][string]$Level, [Parameter(Mandatory = $true)][string]$Out,
      [int]$TimeoutMin = 40,
      [string]$Game = "G:\SteamLibrary\steamapps\common\BeamNG.drive",
      [string]$User = "C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current")
# PowerShell names ignore case: no other variable may be called $level, $out, $game or $user
$here = $PSScriptRoot
if (Get-Process "BeamNG.drive.x64" -ErrorAction SilentlyContinue) { throw "BeamNG is running: close it first" }
New-Item -ItemType Directory -Force $Out | Out-Null
$extDir = Join-Path $User "lua\ge\extensions\ticino"
New-Item -ItemType Directory -Force $extDir | Out-Null
$extFile = Join-Path $extDir "autotest.lua"
Copy-Item (Join-Path $here "autotest.lua") $extFile -Force
$routeFile = Join-Path $User "ticino_test_route.json"
Copy-Item (Join-Path $here "route.json") $routeFile -Force
$work = Join-Path $User "ticino_test"
if (Test-Path $work) { Remove-Item $work -Recurse -Force -Confirm:$false }
$perf = Join-Path $User "ticino_perf.csv"
if (Test-Path $perf) { Remove-Item $perf -Force -Confirm:$false }
$beamLog = Join-Path $User "beamng.log"

$csv = Join-Path $Out "memory.csv"
"seconds,working_set_mb,private_mb,gpu_dedicated_mb,gpu_used_total_mb" | Set-Content $csv
$nvsmi = (Get-Command nvidia-smi -ErrorAction SilentlyContinue).Source

$t0 = Get-Date
$proc = Start-Process -FilePath (Join-Path $Game "Bin64\BeamNG.drive.x64.exe") -WorkingDirectory $Game `
        -ArgumentList "-level $Level/main.level.json -onLevelLoad_ext ticino_autotest" -PassThru
try {
    while (((Get-Date) - $t0).TotalMinutes -lt $TimeoutMin) {
        Start-Sleep -Seconds 2
        $g = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
        if (-not $g) { break }
        $ded = -1
        try {
            $s = (Get-Counter "\GPU Process Memory(pid_$($proc.Id)_*)\Dedicated Usage" -ErrorAction Stop).CounterSamples
            $ded = [math]::Round(($s | Measure-Object CookedValue -Sum).Sum / 1MB)
        } catch {}
        $tot = if ($nvsmi) { [int](& $nvsmi --query-gpu=memory.used --format=csv,noheader,nounits) } else { -1 }
        "{0},{1},{2},{3},{4}" -f [math]::Round(((Get-Date) - $t0).TotalSeconds), [math]::Round($g.WorkingSet64 / 1MB),
            [math]::Round($g.PrivateMemorySize64 / 1MB), $ded, $tot | Add-Content $csv
        if (Test-Path (Join-Path $work "done.txt")) { Start-Sleep -Seconds 20; break }
    }
} finally {
    if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $proc.Id -Force -Confirm:$false; Start-Sleep 5 }
    Remove-Item $extFile -Force -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $routeFile -Force -Confirm:$false -ErrorAction SilentlyContinue
}
"run took {0:N0} s" -f ((Get-Date) - $t0).TotalSeconds | Set-Content (Join-Path $Out "run.txt")
if (Test-Path $work) { Copy-Item (Join-Path $work "*") $Out -Recurse -Force; Remove-Item $work -Recurse -Force -Confirm:$false }
if (Test-Path $perf) { Copy-Item $perf $Out -Force; Remove-Item $perf -Force -Confirm:$false }
Copy-Item $beamLog (Join-Path $Out "beamng.log") -Force
$m = Import-Csv $csv
function Peak($col) { ($m | ForEach-Object { [int]$_.$col } | Measure-Object -Maximum).Maximum }
if ($m) {
    "peak working set {0} MB, peak private {1} MB, peak GPU dedicated {2} MB, peak GPU used (all) {3} MB" -f `
        (Peak "working_set_mb"), (Peak "private_mb"), (Peak "gpu_dedicated_mb"), (Peak "gpu_used_total_mb") |
        Tee-Object (Join-Path $Out "memory_peak.txt")
}
Select-String -Path (Join-Path $Out "beamng.log") -Pattern "Level loaded in|ticino|Failed to load|NO-MATERIAL|Direct3D|error" |
    Select-Object -Last 300 | ForEach-Object { $_.Line } | Set-Content (Join-Path $Out "log_lines.txt")
Get-Content (Join-Path $Out "log_lines.txt") | Select-Object -Last 40
