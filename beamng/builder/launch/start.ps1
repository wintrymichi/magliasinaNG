# Switzerland Builder for Windows (Windows PowerShell 5.1 or PowerShell 7): on the first start it sets up its own Python
# with micromamba (conda-forge), then runs the app and opens it in the browser. Nothing has to be installed beforehand.
# Started by "Start Switzerland Builder.bat" at the top of the repository.
#
#   start.ps1                     the app (http://127.0.0.1:8765)
#   start.ps1 --no-browser        the app without opening the browser
#   start.ps1 cli <command> ...   the command line (python -m app.cli: check, build, resume)
#   $env:SWISSBUILDER_RUNTIME     keeps micromamba, the Python environment and the settings there
#
# PowerShell variable names ignore case: every name below is used for one thing only (CLAUDE.md, $w/$W). No param()
# block: an advanced script would refuse "--no-browser" as an unknown parameter; $args takes every word as it is.
$AppArgs = @($args)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'            # Invoke-WebRequest is many times slower with its progress bar
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

$LaunchDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuilderDir = Split-Path -Parent $LaunchDir
$MmPinned = '2.10.0-0'                              # the conda-forge build taken when the first sources fail

$RuntimeDir = $env:SWISSBUILDER_RUNTIME
if (-not $RuntimeDir) {
    $RuntimeDir = Join-Path $BuilderDir '.runtime'
    # conda packages break on spaces and non-ASCII letters in their own path (a user name like "Mario Rossi")
    if ($RuntimeDir -match '[^\x21-\x7E]') { $RuntimeDir = Join-Path $env:SystemDrive 'SwissBuilder\runtime' }
}
$env:SWISSBUILDER_RUNTIME = $RuntimeDir
$env:MAMBA_ROOT_PREFIX = Join-Path $RuntimeDir 'mamba'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$MmExe = Join-Path $RuntimeDir 'bin\micromamba.exe'
$EnvDir = Join-Path $RuntimeDir 'env'
$YmlFile = Join-Path $BuilderDir 'environment.yml'
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeDir 'bin') | Out-Null

function Say([string]$Text) { Write-Host ''; Write-Host "  $Text" }

function Get-Download([string]$Url, [string]$Dest) {
    for ($attempt = 1; $attempt -le 4; $attempt++) {
        try {
            if (Test-Path $Dest) { Remove-Item -Force $Dest }
            $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
            if ($curl) {
                & $curl.Source -fsSL --connect-timeout 20 -o $Dest $Url
                if ($LASTEXITCODE -eq 0 -and (Test-Path $Dest)) { return $true }
            } else {
                Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
                if (Test-Path $Dest) { return $true }
            }
        } catch { }
        Start-Sleep -Seconds (3 * $attempt)
    }
    return $false
}

try {
    if (-not (Test-Path $MmExe)) {
        Say 'Downloading micromamba, the installer of the app''s Python...'
        $MmPart = "$MmExe.part"
        $got = Get-Download 'https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64' $MmPart
        if (-not $got) {
            $Unpack = Join-Path $RuntimeDir 'mm_unpack'
            if (Test-Path $Unpack) { Remove-Item -Recurse -Force $Unpack }
            New-Item -ItemType Directory -Force -Path $Unpack | Out-Null
            $Tarball = Join-Path $Unpack 'mm.tar.bz2'
            $got = (Get-Download 'https://micro.mamba.pm/api/micromamba/win-64/latest' $Tarball) -or `
                   (Get-Download "https://conda.anaconda.org/conda-forge/win-64/micromamba-$MmPinned.tar.bz2" $Tarball)
            if ($got) {
                & tar.exe -xjf $Tarball -C $Unpack 'Library/bin/micromamba.exe'
                Move-Item -Force (Join-Path $Unpack 'Library\bin\micromamba.exe') $MmPart
            }
            Remove-Item -Recurse -Force $Unpack -ErrorAction SilentlyContinue
        }
        if (-not (Test-Path $MmPart) -or (Get-Item $MmPart).Length -lt 1MB) {
            throw 'micromamba could not be downloaded: check the internet connection and start again.'
        }
        Move-Item -Force $MmPart $MmExe
    }

    $Hash = (Get-FileHash -Algorithm SHA256 -Path $YmlFile).Hash.ToLower()
    $Stamp = Join-Path $EnvDir '.swissbuilder-env'
    $Have = ''
    if (Test-Path $Stamp) { $Have = (Get-Content -Raw -Path $Stamp).Trim() }
    if ($Have -ne $Hash) {
        Say 'Setting up Python and the map libraries (first start only: 5-10 minutes, about 2 GB)...'
        if (Test-Path $EnvDir) { Remove-Item -Recurse -Force $EnvDir }
        & $MmExe create -y -q -p $EnvDir -f $YmlFile
        if ($LASTEXITCODE -ne 0) {
            throw 'The Python environment could not be made (see the messages above). Start again: it goes on where it stopped.'
        }
        Set-Content -Path $Stamp -Value $Hash -Encoding Ascii
        & $MmExe clean -y -q --tarballs | Out-Null
    }

    Set-Location $BuilderDir
    if ($AppArgs.Count -gt 0 -and $AppArgs[0] -eq 'cli') {
        $Rest = @()
        if ($AppArgs.Count -gt 1) { $Rest = $AppArgs[1..($AppArgs.Count - 1)] }
        & $MmExe run -p $EnvDir python -m app.cli @Rest
    } else {
        & $MmExe run -p $EnvDir python -m app.server @AppArgs
    }
    exit $LASTEXITCODE
} catch {
    Write-Host ''
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ''
    exit 1
}
