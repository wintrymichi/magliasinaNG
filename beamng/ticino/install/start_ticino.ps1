<#
  Starts BeamNG.drive straight into the Ticino map with, beside it, the Ticino server (ticino_server.exe, when the
  map was installed in server mode: install.json "mode": "server") or, if the settings allow it, the streaming helper
  (ticino_helper.exe). Both stop by themselves when the game ends. Installed by install_ticino.ps1 into
  <user folder>\ticino_tools with install.json (game and user folder, mode, data folder).
    start_ticino.ps1                 game + server or helper
    start_ticino.ps1 -NoHelper       game only
    start_ticino.ps1 -Menu           to the game's main menu instead of the map
#>
param([switch]$NoHelper, [switch]$Menu)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$info = Get-Content (Join-Path $here 'install.json') -Raw | ConvertFrom-Json
$gameDir = $info.game
$userDir = $info.user
$exe = Join-Path $gameDir 'Bin64\BeamNG.drive.x64.exe'
if (-not (Test-Path $exe)) { throw "BeamNG not found at ${exe}: run the installer again with -GameFolder <path>." }

$serverExe = Join-Path $here 'ticino_server.exe'
$serveMode = $info.PSObject.Properties['mode'] -and $info.mode -eq 'server'
$useHelper = (-not $NoHelper) -and (-not $serveMode)
$settingsPath = Join-Path $userDir 'settings\ticino.json'
if (Test-Path $settingsPath) {
    try {
        $cfg = Get-Content $settingsPath -Raw | ConvertFrom-Json
        if ($cfg.PSObject.Properties['helper'] -and -not $cfg.helper) { $useHelper = $false }
    } catch { Write-Host "settings\ticino.json is not valid JSON: the game ignores it too." -ForegroundColor Yellow }
}

$running = Get-Process -Name 'BeamNG.drive.x64' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($running) {
    Write-Host 'BeamNG is already running: only the server or helper is started.' -ForegroundColor Yellow
    $proc = $running
} else {
    $gameArgs = @()
    if (-not $Menu) { $gameArgs = @('-level', 'ticino/main.level.json') }
    if ($gameArgs.Count) { $proc = Start-Process -FilePath $exe -ArgumentList $gameArgs -WorkingDirectory $gameDir -PassThru }
    else { $proc = Start-Process -FilePath $exe -WorkingDirectory $gameDir -PassThru }
    # Steam may start the game again in a process of its own: follow the one that runs
    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Seconds 3
        $live = Get-Process -Name 'BeamNG.drive.x64' -ErrorAction SilentlyContinue | Select-Object -First 1
    } while (-not $live -and (Get-Date) -lt $deadline)
    if ($live) { $proc = $live }
}

if ($serveMode) {
    if (-not (Test-Path $serverExe)) {
        Write-Host 'ticino_server.exe is missing: run the installer again (without it the map finds no zones).' -ForegroundColor Red
    } elseif (Get-Process -Name 'ticino_server' -ErrorAction SilentlyContinue) {
        Write-Host 'The Ticino server is already running (another window or the Ticino app): not started again.' -ForegroundColor Yellow
    } elseif ($proc) {
        # ticino_server.json beside the exe holds the user and data folders; --game-pid ends it with the game
        Start-Process -FilePath $serverExe -ArgumentList @('--game-pid', $proc.Id) -WorkingDirectory $here `
            -WindowStyle Minimized | Out-Null
        Write-Host "Ticino server started beside the game (pid $($proc.Id)); it stops when the game ends." -ForegroundColor Green
    }
}

$helperExe = Join-Path $here 'ticino_helper.exe'
if ($useHelper -and (Test-Path $helperExe) -and $proc) {
    Start-Process -FilePath $helperExe -ArgumentList @('--user', "`"$userDir`"", '--game-pid', $proc.Id) `
        -WorkingDirectory $here -WindowStyle Minimized | Out-Null
    Write-Host "Helper started beside the game (pid $($proc.Id)); it stops when the game ends." -ForegroundColor Green
} elseif ($useHelper) {
    Write-Host 'No helper (not installed): the map works without it.' -ForegroundColor Yellow
}
