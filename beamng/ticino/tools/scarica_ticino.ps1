<#
Scarica tutti gli zip della release bozza "ticino-all" e li installa nella cartella mods di BeamNG.

Uso (PowerShell, BeamNG chiuso):
  powershell -ExecutionPolicy Bypass -File scarica_ticino.ps1
  powershell -ExecutionPolicy Bypass -File scarica_ticino.ps1 -SoloElenco     (mostra cosa farebbe, non scarica)

- Serve gh loggato (la release e' una bozza: senza login non si vede). Cerca gh nel PATH e in
  %LOCALAPPDATA%\Programs\GitHubCLI.
- Gli zip gia' presenti in mods con la stessa dimensione e lo stesso sha256 della release vengono saltati
  (il controllo sha256 si fa una volta sola e si ricorda in ticino_download\verificati.json).
- Ogni zip si scarica prima in ticino_download\<nome>.part accanto a mods (lo stesso disco) e riprende da dove
  si era fermato se il download si interrompe o se si rilancia lo script. Entra in mods solo dopo il controllo sha256.
- Gli zip ticino_*.zip in mods che la release non ha piu' (vecchie versioni, ticino_region_*) vanno in
  ticino_download\vecchi (con -CancellaVecchi vengono cancellati).
- Prima di installare lancia D:\ticino_tools\pulizia_override.ps1 se c'e' (gli override nella cartella utente
  vincono sugli zip). -SvuotaCache cancella anche temp\levels\ticino (shape e texture convertite).
#>
param(
    [string]$Tag = 'ticino-all',
    [string]$Repo = 'wintrymichi/magliasinaNG',
    [string]$ModsDir = (Join-Path $env:LOCALAPPDATA 'BeamNG\BeamNG.drive\current\mods'),
    [string]$PuliziaScript = 'D:\ticino_tools\pulizia_override.ps1',
    [switch]$SoloElenco,
    [switch]$NoPulizia,
    [switch]$SvuotaCache,
    [switch]$CancellaVecchi,
    [int]$Tentativi = 6
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Scrivi([string]$testo, [string]$colore = 'Gray') { Write-Host $testo -ForegroundColor $colore }
function GB([double]$byte) { '{0:N2} GB' -f ($byte / 1GB) }

# --- gh e curl ---------------------------------------------------------------------------------
$ghExe = $null
$ghCmd = Get-Command gh -ErrorAction SilentlyContinue
if ($ghCmd) { $ghExe = $ghCmd.Source }
if (-not $ghExe) {
    foreach ($candidato in @('Programs\GitHubCLI\bin\gh.exe', 'Programs\GitHubCLI\gh.exe')) {
        $p = Join-Path $env:LOCALAPPDATA $candidato
        if (Test-Path $p) { $ghExe = $p; break }
    }
}
if (-not $ghExe) {
    $trovati = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Programs\GitHubCLI') -Filter gh.exe -Recurse -ErrorAction SilentlyContinue
    if ($trovati) { $ghExe = @($trovati)[0].FullName }
}
if (-not $ghExe) { throw 'gh non trovato (PATH o %LOCALAPPDATA%\Programs\GitHubCLI).' }
$curlExe = Join-Path $env:SystemRoot 'System32\curl.exe'
if (-not (Test-Path $curlExe)) { throw "curl.exe non trovato in $curlExe" }

function GhJson([string]$percorso, [string]$filtro) {
    # niente 2>&1: in Windows PowerShell 5.1 con ErrorActionPreference Stop una riga su stderr diventa un errore
    $out = & $ghExe api $percorso --jq $filtro
    if ($LASTEXITCODE -ne 0) { throw "gh api $percorso fallito (codice $LASTEXITCODE)" }
    return (($out | Out-String) | ConvertFrom-Json)
}

$token = (& $ghExe auth token | Out-String).Trim()
if (-not $token) { throw 'gh non e'' loggato: lancia "gh auth login" e riprova.' }

# --- release e asset ---------------------------------------------------------------------------
Scrivi "Cerco la release '$Tag' di $Repo ..."
$release = $null
for ($pagina = 1; $pagina -le 5 -and -not $release; $pagina++) {
    $lista = @(GhJson "repos/$Repo/releases?per_page=100&page=$pagina" '[.[] | {id, tag_name, created_at}]')
    if ($lista.Count -eq 0) { break }
    $release = $lista | Where-Object { $_.tag_name -eq $Tag } | Sort-Object created_at -Descending | Select-Object -First 1
}
if (-not $release) { throw "Release '$Tag' non trovata (bozza: serve gh loggato con accesso al repo)." }

$asset = @()
for ($pagina = 1; $pagina -le 20; $pagina++) {
    $parte = @(GhJson "repos/$Repo/releases/$($release.id)/assets?per_page=100&page=$pagina" '[.[] | {id, name, size, digest}]')
    $asset += $parte
    if ($parte.Count -lt 100) { break }
}
$zip = @($asset | Where-Object { $_.name -like '*.zip' } | Sort-Object name)
if ($zip.Count -eq 0) { throw "La release '$Tag' non ha zip." }
$totale = ($zip | Measure-Object size -Sum).Sum
Scrivi ("Release '{0}' (id {1}): {2} zip, {3}" -f $Tag, $release.id, $zip.Count, (GB $totale)) 'Cyan'

# --- cartelle e stato --------------------------------------------------------------------------
if (-not (Test-Path $ModsDir)) { throw "Cartella mods non trovata: $ModsDir" }
$ModsDir = (Resolve-Path $ModsDir).Path
$scarico = Join-Path (Split-Path $ModsDir -Parent) 'ticino_download'
$vecchiDir = Join-Path $scarico 'vecchi'
$statoFile = Join-Path $scarico 'verificati.json'

$verificati = @{}
if (Test-Path $statoFile) {
    try {
        $letto = Get-Content $statoFile -Raw | ConvertFrom-Json
        foreach ($prop in $letto.PSObject.Properties) { $verificati[$prop.Name] = $prop.Value }
    } catch { Scrivi "verificati.json illeggibile, ricontrollo tutto." 'Yellow' }
}
function SalvaStato {
    $verificati | ConvertTo-Json | Set-Content -Path $statoFile -Encoding ASCII
}

function Sha([object]$a) {
    if ($a.digest -and $a.digest -like 'sha256:*') { return $a.digest.Substring(7).ToLower() }
    return $null
}

# Uno zip in mods e' a posto se ha la dimensione giusta e lo sha256 giusto (gia' verificato o da verificare).
function GiaInstallato([object]$a, [bool]$calcola) {
    $dest = Join-Path $ModsDir $a.name
    if (-not (Test-Path $dest)) { return $false }
    $f = Get-Item $dest
    if ($f.Length -ne [int64]$a.size) { return $false }
    $atteso = Sha $a
    if (-not $atteso) { return $true }
    $chiave = "$atteso|$($f.Length)|$($f.LastWriteTimeUtc.Ticks)"
    if ($verificati[$a.name] -eq $chiave) { return $true }
    if (-not $calcola) { return $null }
    Scrivi "  controllo sha256 di $($a.name) gia' in mods ..."
    $h = (Get-FileHash -Algorithm SHA256 -Path $dest).Hash.ToLower()
    if ($h -ne $atteso) { return $false }
    $verificati[$a.name] = $chiave
    SalvaStato
    return $true
}

# --- piano -------------------------------------------------------------------------------------
$nomi = @{}
foreach ($a in $zip) { $nomi[$a.name] = $true }
$vecchi = @(Get-ChildItem $ModsDir -Filter 'ticino_*.zip' -File | Where-Object { -not $nomi.ContainsKey($_.Name) })

$daFare = @()
$daControllare = 0
foreach ($a in $zip) {
    $stato = GiaInstallato $a $false
    if ($stato -eq $false) { $daFare += $a }
    elseif ($null -eq $stato) { $daControllare++ }
}
$daScaricare = ($daFare | Measure-Object size -Sum).Sum
if (-not $daScaricare) { $daScaricare = 0 }
$giaParziale = 0
foreach ($a in $daFare) {
    $part = Join-Path $scarico ($a.name + '.part')
    if (Test-Path $part) { $giaParziale += (Get-Item $part).Length }
}

Scrivi ("Da scaricare: {0} zip, {1} (gia' scaricato in parte: {2}); da ricontrollare sha256: {3}; vecchi da togliere da mods: {4}" -f `
    $daFare.Count, (GB $daScaricare), (GB $giaParziale), $daControllare, $vecchi.Count) 'Cyan'
foreach ($v in $vecchi) { Scrivi "  vecchio: $($v.Name) ($(GB $v.Length))" }

$disco = (Get-Item $ModsDir).PSDrive
$serve = $daScaricare - $giaParziale
if ($CancellaVecchi) { $serve -= ($vecchi | Measure-Object Length -Sum).Sum }
Scrivi ("Spazio libero su {0}: {1}, serve circa {2}" -f $disco.Name, (GB $disco.Free), (GB ([math]::Max(0, $serve))))

if ($SoloElenco) {
    foreach ($a in $daFare) { Scrivi ("  scaricherei {0} ({1})" -f $a.name, (GB $a.size)) }
    Scrivi 'Solo elenco: non ho toccato niente.' 'Green'
    exit 0
}

if ($disco.Free -lt $serve + 2GB) {
    throw ("Spazio insufficiente su {0}: libero {1}, servono {2} + 2 GB di margine. Libera spazio (o usa -CancellaVecchi) e rilancia." -f `
        $disco.Name, (GB $disco.Free), (GB $serve))
}

$giocoAperto = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'BeamNG*' }
if ($giocoAperto) { throw 'BeamNG e'' aperto: chiudilo prima (il gioco tiene aperti gli zip in mods).' }

New-Item -ItemType Directory -Force -Path $scarico | Out-Null

# --- pulizia override e cache ------------------------------------------------------------------
if (-not $NoPulizia) {
    if (Test-Path $PuliziaScript) {
        Scrivi "Lancio $PuliziaScript ..." 'Cyan'
        & powershell -NoProfile -ExecutionPolicy Bypass -File $PuliziaScript
        if ($LASTEXITCODE -ne 0) { throw "$PuliziaScript e' finito con errore $LASTEXITCODE" }
    } else {
        Scrivi "$PuliziaScript non c'e': salto la pulizia degli override." 'Yellow'
    }
}
if ($SvuotaCache) {
    $cache = Join-Path $env:LOCALAPPDATA 'BeamNG\BeamNG.drive\current\temp\levels\ticino'
    if (Test-Path $cache) {
        Scrivi "Cancello la cache $cache ..." 'Cyan'
        Remove-Item $cache -Recurse -Force
    }
}

# --- vecchi zip fuori da mods ------------------------------------------------------------------
foreach ($v in $vecchi) {
    if ($CancellaVecchi) {
        Scrivi "Cancello $($v.Name)"
        Remove-Item $v.FullName -Force
    } else {
        New-Item -ItemType Directory -Force -Path $vecchiDir | Out-Null
        Scrivi "Sposto $($v.Name) in $vecchiDir"
        Move-Item $v.FullName (Join-Path $vecchiDir $v.Name) -Force
    }
}

# --- download ----------------------------------------------------------------------------------
$saltati = 0
$scaricati = 0
$falliti = @()
$i = 0
foreach ($a in $zip) {
    $i++
    $titolo = "[{0}/{1}] {2} ({3})" -f $i, $zip.Count, $a.name, (GB $a.size)
    if (GiaInstallato $a $true) {
        Scrivi "$titolo gia' in mods, salto" 'DarkGray'
        $saltati++
        continue
    }
    Scrivi $titolo 'Cyan'
    $part = Join-Path $scarico ($a.name + '.part')
    $dest = Join-Path $ModsDir $a.name
    $atteso = Sha $a
    $ok = $false
    for ($t = 1; $t -le $Tentativi -and -not $ok; $t++) {
        $fatto = 0
        if (Test-Path $part) { $fatto = (Get-Item $part).Length }
        if ($fatto -gt [int64]$a.size) { Remove-Item $part -Force; $fatto = 0 }
        if ($fatto -lt [int64]$a.size) {
            if ($fatto -gt 0) { Scrivi ("  riprendo da {0}" -f (GB $fatto)) }
            $url = "https://api.github.com/repos/$Repo/releases/assets/$($a.id)"
            & $curlExe -L --fail --progress-bar -C - --retry 3 --retry-delay 10 `
                -H "Authorization: Bearer $token" -H 'Accept: application/octet-stream' -H 'User-Agent: magliasina-scarica-ticino' `
                -o $part $url
            if ($LASTEXITCODE -ne 0) {
                Scrivi ("  curl errore {0} (tentativo {1}/{2}), riprovo fra {3} s" -f $LASTEXITCODE, $t, $Tentativi, (15 * $t)) 'Yellow'
                Start-Sleep -Seconds (15 * $t)
                continue
            }
        }
        $fatto = (Get-Item $part).Length
        if ($fatto -ne [int64]$a.size) {
            Scrivi ("  dimensione {0} invece di {1}, riprovo" -f $fatto, $a.size) 'Yellow'
            continue
        }
        if ($atteso) {
            Scrivi '  controllo sha256 ...'
            $h = (Get-FileHash -Algorithm SHA256 -Path $part).Hash.ToLower()
            if ($h -ne $atteso) {
                Scrivi "  sha256 sbagliato, lo riscarico da capo" 'Yellow'
                Remove-Item $part -Force
                continue
            }
        }
        Move-Item $part $dest -Force
        $f = Get-Item $dest
        if ($atteso) { $verificati[$a.name] = "$atteso|$($f.Length)|$($f.LastWriteTimeUtc.Ticks)"; SalvaStato }
        $ok = $true
    }
    if ($ok) { $scaricati++; Scrivi '  ok' 'Green' }
    else { $falliti += $a.name; Scrivi "  NON riuscito dopo $Tentativi tentativi (il .part resta, rilancia lo script per riprendere)" 'Red' }
}

Scrivi ''
Scrivi ("Fatto: {0} scaricati, {1} gia' a posto, {2} falliti." -f $scaricati, $saltati, $falliti.Count) $(if ($falliti.Count) { 'Red' } else { 'Green' })
foreach ($n in $falliti) { Scrivi "  fallito: $n" 'Red' }
if ($vecchi.Count -and -not $CancellaVecchi) { Scrivi "I vecchi zip sono in ${vecchiDir}: cancellali quando il nuovo livello funziona." 'Yellow' }
if ($falliti.Count) { exit 1 }
exit 0
