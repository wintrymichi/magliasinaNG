<#
.SYNOPSIS
  Installs, updates or removes the Ticino map for BeamNG.drive (beamng/ticino/README.md).

.DESCRIPTION
  Downloads every zip of a Ticino release into the game's mods folder, checks each one by its sha256, resumes broken
  downloads, moves out old Ticino zips, removes leftover user-folder overrides of the level, clears the game's cache
  of the level when the version changes, installs the streaming helper and a "Start Ticino" shortcut, and writes the
  settings file (settings\ticino.json) if there is none. The Malcantone map (magliaso_pura) is never touched.
  Run it again to update: only what changed is downloaded.

  Double-click "Install Ticino.bat", or in PowerShell:
    powershell -ExecutionPolicy Bypass -File install_ticino.ps1                 install or update
    powershell -ExecutionPolicy Bypass -File install_ticino.ps1 -ListOnly       show what it would do
    powershell -ExecutionPolicy Bypass -File install_ticino.ps1 -Uninstall      remove the Ticino map

.PARAMETER Tag
  The release to install. Default: the tag in release.txt beside this script (the release the installer came with),
  else ticino-v1. A draft release needs gh (GitHub CLI) logged in to the repository.
#>
param(
    [string]$Tag = '',
    [string]$Repo = 'wintrymichi/magliasinaNG',
    [string]$UserFolder = (Join-Path $env:LOCALAPPDATA 'BeamNG\BeamNG.drive\current'),
    [string]$GameFolder = '',
    [switch]$ListOnly,
    [switch]$Uninstall,
    [switch]$DeleteOld,
    [switch]$NoHelper,
    [switch]$NoShortcut,
    [switch]$KeepCache,
    [int]$Retries = 6
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# PowerShell variable names ignore case: every name below is unique without regard to case.

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Tag) {
    $rel = Join-Path $scriptDir 'release.txt'
    if (Test-Path $rel) { $Tag = (Get-Content $rel -Raw).Trim() }
    if (-not $Tag) { $Tag = 'ticino-v1' }
}

function Say([string]$text, [string]$colour = 'Gray') { Write-Host $text -ForegroundColor $colour }
function GiB([double]$bytes) { '{0:N2} GB' -f ($bytes / 1GB) }

$mods = Join-Path $UserFolder 'mods'
$work = Join-Path $UserFolder 'ticino_download'
$tools = Join-Path $UserFolder 'ticino_tools'
$stateFile = Join-Path $work 'installed.json'
$checkedFile = Join-Path $work 'checked.json'
$settingsFile = Join-Path $UserFolder 'settings\ticino.json'
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Start Ticino (BeamNG).lnk'

if (-not (Test-Path $mods)) {
    throw "BeamNG mods folder not found: $mods. Start the game once, or give the user folder with -UserFolder <path>."
}
$gameRunning = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'BeamNG*' }

# ------------------------------------------------------------------------------------------------ user folder
# Files of the level in the user folder win over the zips: any left from tests or older versions must go.
function Move-Overrides {
    $found = @()
    foreach ($rel in @('levels\ticino', 'lua\ge\extensions\ticino', 'ticino_stream_cfg.json', 'temp\ticino')) {
        $p = Join-Path $UserFolder $rel
        if (Test-Path $p) { $found += $rel }
    }
    if ($found.Count -eq 0) { return }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $backup = Join-Path $work "overrides_$stamp"
    foreach ($rel in $found) {
        $src = Join-Path $UserFolder $rel
        if ($rel -eq 'temp\ticino') {
            Remove-Item $src -Recurse -Force
            continue
        }
        $dst = Join-Path $backup $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
        Move-Item $src $dst -Force
        Say "  moved the override $rel to $backup" 'Yellow'
    }
}

function Clear-LevelCache {
    $cache = Join-Path $UserFolder 'temp\levels\ticino'
    if (Test-Path $cache) {
        Say "Clearing the game's cache of the level ($cache) ..." 'Cyan'
        Remove-Item $cache -Recurse -Force
    }
}

# ------------------------------------------------------------------------------------------------ uninstall
if ($Uninstall) {
    if ($gameRunning) { throw 'BeamNG is running: close it first (the game keeps the zips in mods open).' }
    $zips = @(Get-ChildItem $mods -Filter 'ticino_*.zip' -File)
    Say ("Removing {0} Ticino zips ({1}), the level cache, the helper and the shortcut." -f $zips.Count,
        (GiB (($zips | Measure-Object Length -Sum).Sum))) 'Cyan'
    if ($ListOnly) { Say 'List only: nothing changed.' 'Green'; exit 0 }
    foreach ($z in $zips) { Remove-Item $z.FullName -Force }
    Move-Overrides
    Clear-LevelCache
    foreach ($p in @($tools, $shortcutPath)) { if (Test-Path $p) { Remove-Item $p -Recurse -Force } }
    if (Test-Path $work) { Remove-Item $work -Recurse -Force }
    Say 'Ticino removed. settings\ticino.json is kept (delete it by hand if you like).' 'Green'
    exit 0
}

# ------------------------------------------------------------------------------------------------ GitHub
$curl = Join-Path $env:SystemRoot 'System32\curl.exe'
if (-not (Test-Path $curl)) { throw "curl.exe not found in $curl (Windows 10 1803 or newer has it)." }

$token = $null
$ghExe = $null
$ghCmd = Get-Command gh -ErrorAction SilentlyContinue
if ($ghCmd) { $ghExe = $ghCmd.Source }
if (-not $ghExe) {
    $found = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Programs\GitHubCLI') -Filter gh.exe -Recurse -ErrorAction SilentlyContinue
    if ($found) { $ghExe = @($found)[0].FullName }
}
if ($ghExe) {
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $out = & $ghExe auth token 2>$null
    $ErrorActionPreference = $prevPref
    if ($LASTEXITCODE -eq 0 -and $out) { $token = ($out | Out-String).Trim() }
}

function Api([string]$path) {
    $headers = @{ 'User-Agent' = 'magliasina-ticino-installer'; 'Accept' = 'application/vnd.github+json' }
    if ($token) { $headers['Authorization'] = "Bearer $token" }
    # Windows PowerShell 5.1 returns a JSON array as ONE object when it is returned straight from the call
    # (@(...) then has Count 1 and the asset pages stopped after the first): assign it first.
    $r = Invoke-RestMethod -Uri "https://api.github.com/$path" -Headers $headers
    return $r
}

Say "Looking for the release '$Tag' of $Repo ..."
$release = $null
try { $release = Api "repos/$Repo/releases/tags/$Tag" } catch { $release = $null }
if (-not $release -and $token) {            # drafts are not found by tag
    for ($page = 1; $page -le 5 -and -not $release; $page++) {
        $list = @(Api "repos/$Repo/releases?per_page=100&page=$page")
        if ($list.Count -eq 0) { break }
        $release = $list | Where-Object { $_.tag_name -eq $Tag } | Select-Object -First 1
    }
}
if (-not $release) {
    if ($token) { throw "Release '$Tag' not found in $Repo." }
    throw "Release '$Tag' not found. If it is a draft, install the GitHub CLI and run 'gh auth login' first."
}
$assets = @()
for ($page = 1; $page -le 20; $page++) {
    $part = @(Api "repos/$Repo/releases/$($release.id)/assets?per_page=100&page=$page")
    $assets += $part
    if ($part.Count -lt 100) { break }
}
$zips = @($assets | Where-Object { $_.name -like 'ticino_*.zip' } | Sort-Object name)
$helperAsset = $assets | Where-Object { $_.name -eq 'helper_ticino.zip' } | Select-Object -First 1
if ($zips.Count -eq 0) { throw "The release '$Tag' has no ticino_*.zip." }
$base = $zips | Where-Object { $_.name -like 'ticino_base_*' } | Select-Object -First 1
if (-not $base) { throw "The release '$Tag' has no ticino_base zip." }
$total = ($zips | Measure-Object size -Sum).Sum
Say ("Release '{0}': {1} zips, {2}" -f $Tag, $zips.Count, (GiB $total)) 'Cyan'

# Read the release's assets again: a workflow can replace an asset while the installer runs (new id, the old one
# answers 404).
function Get-Assets {
    $list = @()
    for ($page = 1; $page -le 20; $page++) {
        $part = @(Api "repos/$Repo/releases/$($release.id)/assets?per_page=100&page=$page")
        $list += $part
        if ($part.Count -lt 100) { break }
    }
    return ,$list
}

function Sha([object]$a) {
    if ($a.digest -and "$($a.digest)" -like 'sha256:*') { return "$($a.digest)".Substring(7).ToLower() }
    return $null
}

# ------------------------------------------------------------------------------------------------ state
New-Item -ItemType Directory -Force -Path $work | Out-Null
$checked = @{}
if (Test-Path $checkedFile) {
    try {
        $read = Get-Content $checkedFile -Raw | ConvertFrom-Json
        foreach ($prop in $read.PSObject.Properties) { $checked[$prop.Name] = $prop.Value }
    } catch { Say 'checked.json unreadable: checking every zip again.' 'Yellow' }
}
function Save-Checked { $checked | ConvertTo-Json | Set-Content -Path $checkedFile -Encoding ASCII }

# The zone of a Ticino zip: ticino_<zone>_<n>.zip -> <zone> (ticino_base_<n>.zip -> base)
function Zone-Of([string]$name) {
    if ($name -match '^ticino_(.+)_\d+\.zip$') { return $Matches[1] }
    return $name
}

# A zip in mods is in place when it has the size and the sha256 of the release (checked once, then remembered).
function Test-Installed([object]$a, [bool]$hashNow) {
    $dest = Join-Path $mods $a.name
    if (-not (Test-Path $dest)) { return $false }
    $f = Get-Item $dest
    if ($f.Length -ne [int64]$a.size) { return $false }
    $want = Sha $a
    if (-not $want) { return $true }
    $key = "$want|$($f.Length)|$($f.LastWriteTimeUtc.Ticks)"
    if ($checked[$a.name] -eq $key) { return $true }
    if (-not $hashNow) { return $null }
    Say "  checking the sha256 of $($a.name) already in mods ..."
    $h = (Get-FileHash -Algorithm SHA256 -Path $dest).Hash.ToLower()
    if ($h -ne $want) { return $false }
    $checked[$a.name] = $key
    Save-Checked
    return $true
}

$names = @{}
$relZones = @{}
foreach ($a in $zips) { $names[$a.name] = $true; $relZones[(Zone-Of $a.name)] = $true }
# A zip is old only when the release has zips of its zone (base or a zone) under other names. A zone the release does
# not have at all (a build still uploading, PC test 2026-10-31: ti_2_4 was moved out and the install stopped) is kept.
$notInRelease = @(Get-ChildItem $mods -Filter 'ticino_*.zip' -File | Where-Object { -not $names.ContainsKey($_.Name) })
$old = @($notInRelease | Where-Object { $relZones.ContainsKey((Zone-Of $_.Name)) })
$kept = @($notInRelease | Where-Object { -not $relZones.ContainsKey((Zone-Of $_.Name)) })
foreach ($k in $kept) { Say "  kept: $($k.Name) (its zone is not in the release: the release may be incomplete)" 'Yellow' }
$todo = @()
$toHash = 0
foreach ($a in $zips) {
    $s = Test-Installed $a $false
    if ($s -eq $false) { $todo += $a } elseif ($null -eq $s) { $toHash++ }
}
$need = ($todo | Measure-Object size -Sum).Sum
if (-not $need) { $need = 0 }
$partial = 0
foreach ($a in $todo) {
    $p = Join-Path $work ($a.name + '.part')
    if (Test-Path $p) { $partial += (Get-Item $p).Length }
}
Say ("To download: {0} zips, {1} (already partly downloaded: {2}); sha256 to check: {3}; old Ticino zips to move out: {4}" -f `
    $todo.Count, (GiB $need), (GiB $partial), $toHash, $old.Count) 'Cyan'
foreach ($o in $old) { Say "  old: $($o.Name) ($(GiB $o.Length))" }

$drive = (Get-Item $mods).PSDrive
$space = $need - $partial
if ($DeleteOld) { $space -= ($old | Measure-Object Length -Sum).Sum }
Say ("Free on {0}: {1}, needed about {2} (+ about 15 GB the game uses for its cache of the level)" -f $drive.Name,
    (GiB $drive.Free), (GiB ([math]::Max([double]0, [double]$space))))

if ($ListOnly) {
    foreach ($a in $todo) { Say ("  would download {0} ({1})" -f $a.name, (GiB $a.size)) }
    Say 'List only: nothing changed.' 'Green'
    exit 0
}
if ($drive.Free -lt $space + 2GB) {
    throw ("Not enough space on {0}: {1} free, {2} + 2 GB needed. Free some space (or use -DeleteOld) and run again." -f `
        $drive.Name, (GiB $drive.Free), (GiB $space))
}
if ($gameRunning) { throw 'BeamNG is running: close it first (the game keeps the zips in mods open).' }

# ------------------------------------------------------------------------------------------------ clean up
Move-Overrides
$prevState = $null
if (Test-Path $stateFile) { try { $prevState = Get-Content $stateFile -Raw | ConvertFrom-Json } catch { $prevState = $null } }
$baseSha = Sha $base
if (-not $KeepCache -and (-not $prevState -or $prevState.base -ne "$($base.name)|$baseSha")) { Clear-LevelCache }
foreach ($o in $old) {
    try {
        if ($DeleteOld) {
            Say "Deleting $($o.Name)"
            Remove-Item $o.FullName -Force -ErrorAction Stop
        } else {
            $oldDir = Join-Path $work 'old'
            New-Item -ItemType Directory -Force -Path $oldDir | Out-Null
            Say "Moving $($o.Name) to $oldDir"
            Move-Item $o.FullName (Join-Path $oldDir $o.Name) -Force -ErrorAction Stop
        }
    } catch {
        # one old zip that cannot be moved must not stop the install (the game would load it beside the new ones)
        Say "  could not move $($o.Name): $($_.Exception.Message) (move it out of mods by hand)" 'Red'
    }
}

# ------------------------------------------------------------------------------------------------ download
function Get-Asset([object]$a, [string]$dest) {
    $part = Join-Path $work ($a.name + '.part')
    $want = Sha $a
    for ($t = 1; $t -le $Retries; $t++) {
        $have = 0
        if (Test-Path $part) { $have = (Get-Item $part).Length }
        if ($have -gt [int64]$a.size) { Remove-Item $part -Force; $have = 0 }
        if ($have -lt [int64]$a.size) {
            if ($have -gt 0) { Say ("  resuming at {0}" -f (GiB $have)) }
            if ($token) {
                & $curl -L --fail --progress-bar -C - --retry 3 --retry-delay 10 -H "Authorization: Bearer $token" `
                    -H 'Accept: application/octet-stream' -H 'User-Agent: magliasina-ticino-installer' -o $part `
                    "https://api.github.com/repos/$Repo/releases/assets/$($a.id)"
            } else {
                & $curl -L --fail --progress-bar -C - --retry 3 --retry-delay 10 -H 'User-Agent: magliasina-ticino-installer' `
                    -o $part $a.browser_download_url
            }
            if ($LASTEXITCODE -ne 0) {
                Say ("  curl error {0} (try {1}/{2}), again in {3} s" -f $LASTEXITCODE, $t, $Retries, (15 * $t)) 'Yellow'
                Start-Sleep -Seconds (15 * $t)
                $fresh = $null
                try { $fresh = (Get-Assets) | Where-Object { $_.name -eq $a.name } | Select-Object -First 1 } catch { }
                if ($fresh -and $fresh.id -ne $a.id) {
                    Say '  the asset was replaced on the release: downloading the new one' 'Yellow'
                    if ($fresh.size -ne $a.size -or (Sha $fresh) -ne $want) { Remove-Item $part -Force -ErrorAction SilentlyContinue }
                    $a = $fresh
                    $want = Sha $a
                }
                continue
            }
        }
        $have = (Get-Item $part).Length
        if ($have -ne [int64]$a.size) { Say ("  size {0} instead of {1}, again" -f $have, $a.size) 'Yellow'; continue }
        if ($want) {
            Say '  checking sha256 ...'
            $h = (Get-FileHash -Algorithm SHA256 -Path $part).Hash.ToLower()
            if ($h -ne $want) { Say '  wrong sha256, downloading it again' 'Yellow'; Remove-Item $part -Force; continue }
        }
        Move-Item $part $dest -Force
        return $true
    }
    return $false
}

$done = 0
$skipped = 0
$failed = @()
$i = 0
foreach ($a in $zips) {
    $i++
    $title = "[{0}/{1}] {2} ({3})" -f $i, $zips.Count, $a.name, (GiB $a.size)
    if (Test-Installed $a $true) { Say "$title in place" 'DarkGray'; $skipped++; continue }
    Say $title 'Cyan'
    $dest = Join-Path $mods $a.name
    if (Get-Asset $a $dest) {
        $f = Get-Item $dest
        $want = Sha $a
        if ($want) { $checked[$a.name] = "$want|$($f.Length)|$($f.LastWriteTimeUtc.Ticks)"; Save-Checked }
        $done++
        Say '  ok' 'Green'
    } else {
        $failed += $a.name
        Say "  FAILED after $Retries tries (the .part stays: run the installer again to resume)" 'Red'
    }
}

# ------------------------------------------------------------------------------------------------ mods enabled
# After a game update BeamNG turns every mod off in mods\db.json: turn the Ticino zips back on.
$db = Join-Path $mods 'db.json'
if (Test-Path $db) {
    try {
        $text = Get-Content $db -Raw
        $j = $text | ConvertFrom-Json
        $changed = 0
        if ($j.mods) {
            foreach ($prop in $j.mods.PSObject.Properties) {
                $m = $prop.Value
                if ($prop.Name -like 'ticino_*' -and $m.PSObject.Properties['active'] -and -not $m.active) {
                    $m.active = $true
                    $changed++
                }
            }
        }
        if ($changed) {
            Copy-Item $db (Join-Path $work 'db.json.bak') -Force
            $json = $j | ConvertTo-Json -Depth 50
            [IO.File]::WriteAllText($db, $json, (New-Object System.Text.UTF8Encoding $false))   # no BOM
            Say "Turned $changed Ticino mods back on in mods\db.json (copy of the old file in $work)." 'Yellow'
        }
    } catch { Say "mods\db.json not read ($($_.Exception.Message)): check in the game's Mods menu that the Ticino mods are on." 'Yellow' }
}

# ------------------------------------------------------------------------------------------------ game folder
function Find-Game {
    if ($GameFolder) { return $GameFolder }
    $steam = $null
    try { $steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction Stop).SteamPath } catch { $steam = $null }
    $libs = @()
    if ($steam) {
        $libs += $steam
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (Test-Path $vdf) {
            foreach ($line in Get-Content $vdf) {
                if ($line -match '"path"\s+"([^"]+)"') { $libs += ($Matches[1] -replace '\\\\', '\') }
            }
        }
    }
    foreach ($lib in $libs) {
        $g = Join-Path $lib 'steamapps\common\BeamNG.drive'
        if (Test-Path (Join-Path $g 'Bin64\BeamNG.drive.x64.exe')) { return $g }
    }
    return $null
}
$game = Find-Game
if (-not $game) { Say 'BeamNG.drive not found in the Steam libraries: give it with -GameFolder <path> for the shortcut.' 'Yellow' }

# ------------------------------------------------------------------------------------------------ helper, shortcut
New-Item -ItemType Directory -Force -Path $tools | Out-Null
foreach ($f in @('start_ticino.ps1', 'Start Ticino.bat')) {
    $src = Join-Path $scriptDir $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $tools $f) -Force }
}
if (-not $NoHelper -and $helperAsset) {
    $hzip = Join-Path $work 'helper_ticino.zip'
    $hkey = Sha $helperAsset
    $hstamp = Join-Path $tools 'helper.sha256'
    $have = $null
    if (Test-Path $hstamp) { $have = (Get-Content $hstamp -Raw).Trim() }
    if ($have -ne $hkey -or -not (Test-Path (Join-Path $tools 'ticino_helper.exe'))) {
        Say 'Streaming helper ...' 'Cyan'
        if (Get-Asset $helperAsset $hzip) {
            Expand-Archive -Path $hzip -DestinationPath $tools -Force
            Remove-Item $hzip -Force
            if ($hkey) { Set-Content -Path $hstamp -Value $hkey -Encoding ASCII }
            Say '  ok' 'Green'
        } else { Say '  helper not downloaded: the map works without it (a bit slower at terrain moves).' 'Yellow' }
    }
}
$installInfo = [ordered]@{ tag = $Tag; base = "$($base.name)|$baseSha"; game = $game; user = $UserFolder
                            installed = (Get-Date).ToString('s') }
$installInfo | ConvertTo-Json | Set-Content -Path $stateFile -Encoding ASCII
$installInfo | ConvertTo-Json | Set-Content -Path (Join-Path $tools 'install.json') -Encoding ASCII

if (-not (Test-Path $settingsFile)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $settingsFile -Parent) | Out-Null
    $defaults = [ordered]@{ preset = 'standard'; helper = $true; diagnostics = $false }
    $defaults | ConvertTo-Json | Set-Content -Path $settingsFile -Encoding ASCII
    Say "Settings written to $settingsFile (preset 'standard'; 'light' for weaker PCs)." 'Cyan'
}

if (-not $NoShortcut -and $game -and (Test-Path (Join-Path $tools 'Start Ticino.bat'))) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($shortcutPath)
    $lnk.TargetPath = Join-Path $tools 'Start Ticino.bat'
    $lnk.WorkingDirectory = $tools
    $lnk.IconLocation = (Join-Path $game 'Bin64\BeamNG.drive.x64.exe') + ',0'
    $lnk.WindowStyle = 7
    $lnk.Save()
    Say "Shortcut on the desktop: $shortcutPath" 'Cyan'
}

Say ''
Say ("Done: {0} downloaded, {1} already in place, {2} failed." -f $done, $skipped, $failed.Count) $(if ($failed.Count) { 'Red' } else { 'Green' })
foreach ($n in $failed) { Say "  failed: $n" 'Red' }
if ($old.Count -and -not $DeleteOld) { Say "The old zips are in $work\old: delete them once the new version runs." 'Yellow' }
if ($failed.Count) { exit 1 }
Say 'Start the map with "Start Ticino (BeamNG)" on the desktop, or in the game: Freeroam > Ticino.' 'Green'
Say 'The first start after an install mounts the new zips and can show "not responding" for a minute or two: wait.' 'Yellow'
exit 0
