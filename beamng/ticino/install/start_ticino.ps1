<#
  Starts BeamNG.drive straight into the Ticino map and, if the settings allow it, the streaming helper
  (ticino_helper.exe) beside it. The helper stops by itself when the game ends. Installed by install_ticino.ps1
  into <user folder>\ticino_tools with install.json (game and user folder).
    start_ticino.ps1                 game + helper
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

$useHelper = -not $NoHelper
$settingsPath = Join-Path $userDir 'settings\ticino.json'
if (Test-Path $settingsPath) {
    try {
        $cfg = Get-Content $settingsPath -Raw | ConvertFrom-Json
        if ($cfg.PSObject.Properties['helper'] -and -not $cfg.helper) { $useHelper = $false }
    } catch { Write-Host "settings\ticino.json is not valid JSON: the game ignores it too." -ForegroundColor Yellow }
}

$running = Get-Process -Name 'BeamNG.drive.x64' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($running) {
    Write-Host 'BeamNG is already running: only the helper is started.' -ForegroundColor Yellow
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

$helperExe = Join-Path $here 'ticino_helper.exe'
if ($useHelper -and (Test-Path $helperExe) -and $proc) {
    Start-Process -FilePath $helperExe -ArgumentList @('--user', "`"$userDir`"", '--game-pid', $proc.Id) `
        -WorkingDirectory $here -WindowStyle Minimized | Out-Null
    Write-Host "Helper started beside the game (pid $($proc.Id)); it stops when the game ends." -ForegroundColor Green
} elseif ($useHelper) {
    Write-Host 'No helper (not installed): the map works without it.' -ForegroundColor Yellow
}
