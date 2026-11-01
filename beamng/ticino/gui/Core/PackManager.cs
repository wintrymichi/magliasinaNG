using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace TicinoServer.Core;

/// <summary>The zips of a Ticino release on GitHub against what is on this PC: the base pack in BeamNG's mods, the
/// zone packs in the packs folder (server mode) or in mods too (packs mode, see <see cref="PacksMode"/>), the server
/// program beside the installer's or in %LOCALAPPDATA%\TicinoServer\server. A zone counts wherever it is, in either
/// folder (as install_ticino.ps1 looks for it). Downloads resume (name.part), every zip is checked by the sha256
/// GitHub keeps for it (or by the installer's checked.json), and a downloaded zip (name.ready) goes into place only
/// while the server and the game are not running (they keep the zips open). Same rules as install_ticino.ps1: a zip
/// whose zone the release has under another name is old; a zone the release has no zip of at all is kept.</summary>
public sealed partial class PackManager : Observable
{
    public const string ServerAsset = "server_ticino.zip";
    public const string GameOpenReason = "BeamNG is open";
    public const string ServerRunningReason = "the server is running";

    readonly AppConfig cfg;
    readonly GitHub gh = new();
    CancellationTokenSource? cts;
    State st = new();

    public PackManager(AppConfig cfg)
    {
        this.cfg = cfg;
    }

    public ObservableCollection<PackItem> Items { get; } = new();
    public Func<bool> ServerRunning { get; set; } = () => false;
    public event Action? Applied;

    Release? release;
    public Release? Release { get => release; private set => Set(ref release, value); }

    string? error;
    public string? Error { get => error; private set => Set(ref error, value); }

    bool checking;
    public bool Checking { get => checking; private set => Set(ref checking, value); }

    bool busy;
    public bool Busy { get => busy; private set { if (Set(ref busy, value)) Raise(nameof(CanDownload)); } }

    double overall;
    public double Overall { get => overall; private set => Set(ref overall, value); }

    string progressText = "";
    public string ProgressText { get => progressText; private set => Set(ref progressText, value); }

    string summary = "Not checked yet.";
    public string Summary { get => summary; private set => Set(ref summary, value); }

    int needCount;
    public int NeedCount { get => needCount; private set { if (Set(ref needCount, value)) Raise(nameof(CanDownload)); } }

    long needBytes;
    public long NeedBytes { get => needBytes; private set => Set(ref needBytes, value); }

    int readyCount;
    public int ReadyCount { get => readyCount; private set => Set(ref readyCount, value); }

    int installedZones;
    public int InstalledZones { get => installedZones; private set => Set(ref installedZones, value); }

    int releaseZones;
    public int ReleaseZones { get => releaseZones; private set => Set(ref releaseZones, value); }

    int uncheckedCount;
    /// <summary>Zips in place whose sha256 is not checked yet (<see cref="Verify"/> checks them, no download).</summary>
    public int UncheckedCount { get => uncheckedCount; private set => Set(ref uncheckedCount, value); }

    bool moving;
    /// <summary>Zips are being moved (from mods, or to a new packs folder): <see cref="MoveText"/> says how far.</summary>
    public bool Moving { get => moving; private set => Set(ref moving, value); }

    string moveText = "";
    public string MoveText { get => moveText; private set => Set(ref moveText, value); }

    public bool CanDownload => !Busy && NeedCount > 0;

    /// <summary>Zone zips in BeamNG's mods (an install made without the server): the game mounts every one of them
    /// at each start (75-81 s), and with the server they belong in the data folder.</summary>
    public List<FileInfo> ZonesInMods { get; private set; } = new();

    /// <summary>Old zips of this PC: zones the release has under another name.</summary>
    public List<FileInfo> OldZips { get; private set; } = new();

    public string? DataFolder => string.IsNullOrWhiteSpace(cfg.DataFolder) ? null : cfg.DataFolder;

    /// <summary>The installer's "packs" way: every zip in BeamNG's mods, mounted by the game at its start, no server
    /// (install.json "mode": "packs", or without the installer zones in mods and none in the packs folder). The app
    /// then keeps the zones in mods and Play starts the game alone, as "Start Ticino" does.</summary>
    public bool PacksMode { get => packsMode; private set => Set(ref packsMode, value); }
    bool packsMode;

    /// <summary>Where new zone zips go: mods in packs mode, else the packs folder (null until it is chosen).</summary>
    public string? ZoneHome => PacksMode ? BeamNG.Mods(cfg) : DataFolder;

    /// <summary>The installer's work folder (its .part files, checked.json, old zips).</summary>
    string Work => Path.Combine(BeamNG.UserFolder(cfg), "ticino_download");
    // packs mode: beside the installer's, on the disk of mods (installing a zip is a rename)
    // (and before a packs folder is chosen: only the base and the server can be downloaded then)
    string DownloadDir => PacksMode || DataFolder is null ? Path.Combine(Work, "app") : Path.Combine(DataFolder, ".download");
    /// <summary>The app's own copy of the server, used when the installer has not set up this user folder.</summary>
    public static string OwnServerDir => Path.Combine(AppConfig.Dir, "server");

    /// <summary>Where the server program goes: the installer's ticino_tools when it has set up this user folder
    /// (one exe for the app and "Start Ticino"), else the app's own folder.</summary>
    public string ServerHome => Installer.Present(cfg) ? Installer.ToolsDir(cfg) : OwnServerDir;

    [GeneratedRegex(@"^ticino_(.+)_\d+\.zip$", RegexOptions.IgnoreCase)]
    private static partial Regex ZoneName();

    public static string ZoneOf(string name)
    {
        var m = ZoneName().Match(name);
        return m.Success ? m.Groups[1].Value : name;
    }

    // ------------------------------------------------------------------------------------------- state file
    sealed class State
    {
        public Dictionary<string, string> Checked { get; set; } = new();
        public string? Base { get; set; }
        public string? Server { get; set; }
        public string? ServerDir { get; set; }
    }

    static string? StampOf(string path)
    {
        try { return File.Exists(path) ? File.ReadAllText(path).Trim().ToLowerInvariant() : null; }
        catch { return null; }
    }

    // one place for every mode and packs folder (1.0.0 kept it in the packs folder's .download, read once from there)
    static string StatePath => Path.Combine(AppConfig.Dir, "state.json");

    void LoadState()
    {
        try
        {
            string path = StatePath;
            if (!File.Exists(path) && DataFolder != null && File.Exists(Path.Combine(DataFolder, ".download", "state.json")))
                path = Path.Combine(DataFolder, ".download", "state.json");
            st = File.Exists(path) ? JsonSerializer.Deserialize<State>(File.ReadAllText(path)) ?? new() : new();
        }
        catch { st = new(); }
    }

    /// <summary>The installer's checked.json: zip name -> "sha256|length|LastWriteTimeUtc.Ticks" (the format of
    /// <see cref="Key"/>), so a zip it has hashed is not hashed again.</summary>
    Dictionary<string, string> InstallerChecked()
    {
        var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            string f = Path.Combine(Work, "checked.json");
            if (File.Exists(f) && JsonNode.Parse(File.ReadAllText(f)) is JsonObject o)
                foreach (var (k, v) in o)
                    if (v is JsonValue jv && jv.TryGetValue(out string? s) && s != null) d[k] = s;
        }
        catch (Exception e) { Log.Write("installer's checked.json not read: " + e.Message); }
        return d;
    }

    void SaveState()
    {
        try { Files.WriteAtomic(StatePath, JsonSerializer.Serialize(st, new JsonSerializerOptions { WriteIndented = true })); }
        catch (Exception e) { Log.Write("state.json not written: " + e.Message); }
    }

    static string Key(string sha, FileInfo f) => $"{sha}|{f.Length}|{f.LastWriteTimeUtc.Ticks}";

    // ------------------------------------------------------------------------------------------- where things go
    /// <summary>Where the zip is on this PC (a zone in the packs folder or in mods), else where it would go.</summary>
    string? Dest(PackItem it) => it.Kind switch
    {
        PackKind.Base => Path.Combine(BeamNG.Mods(cfg), it.Name),
        PackKind.Zone => Found(it.Name) ?? Target(it),
        _ => null,
    };

    string? Target(PackItem it) => ZoneHome is null ? null : Path.Combine(ZoneHome, it.Name);

    string? Found(string name)
    {
        foreach (var dir in new[] { DataFolder, BeamNG.Mods(cfg) })
            if (dir != null && File.Exists(Path.Combine(dir, name))) return Path.Combine(dir, name);
        return null;
    }

    string ReadyPath(PackItem it) => Path.Combine(DownloadDir, it.Name + ".ready");
    string PartPath(PackItem it) => Path.Combine(DownloadDir, it.Name + ".part");

    /// <summary>The server program to run: beside the app (a developer's copy), the installer's, the app's own.</summary>
    public static string? ServerExe(AppConfig c)
    {
        foreach (var dir in new[] { AppContext.BaseDirectory, Installer.Present(c) ? Installer.ToolsDir(c) : null, OwnServerDir })
            if (dir != null && File.Exists(Path.Combine(dir, Installer.ServerExeName)))
                return Path.Combine(dir, Installer.ServerExeName);
        return null;
    }

    /// <summary>Zone zips in the packs folder.</summary>
    IEnumerable<FileInfo> LocalZones()
    {
        if (DataFolder is null || !Directory.Exists(DataFolder)) return Array.Empty<FileInfo>();
        return new DirectoryInfo(DataFolder).EnumerateFiles("ticino_*.zip")
            .Where(f => !f.Name.StartsWith("ticino_base", StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>Zone zips in the packs folder and in mods.</summary>
    List<FileInfo> AllZones()
    {
        var all = LocalZones().ToList();
        string mods = Path.GetFullPath(BeamNG.Mods(cfg));
        if (DataFolder is null || !Path.GetFullPath(DataFolder).Equals(mods, StringComparison.OrdinalIgnoreCase))
            all.AddRange(ZonesInMods);
        return all;
    }

    /// <summary>Zone zips on this PC (packs folder and mods): the number the Home page shows before a check.</summary>
    public int LocalZoneCount()
    {
        try { return AllZones().Count; }
        catch { return 0; }
    }

    /// <summary>Lists the zones in mods and decides the mode (<see cref="PacksMode"/>).</summary>
    public void ScanMods()
    {
        try
        {
            ZonesInMods = Directory.Exists(BeamNG.Mods(cfg))
                ? new DirectoryInfo(BeamNG.Mods(cfg)).EnumerateFiles("ticino_*.zip")
                    .Where(z => !z.Name.StartsWith("ticino_base", StringComparison.OrdinalIgnoreCase)).ToList()
                : new();
        }
        catch { ZonesInMods = new(); }
        Raise(nameof(ZonesInMods));
        // the mode follows where the zones ARE (the game needs them there), install.json's word only on a tie: on
        // the PC of 2026-10-31 an installer of the other mode ran beside the app and install.json said "packs"
        // with every zone in the packs folder, or "server" with them back in mods
        var inst = Installer.Read(cfg);
        int inData = LocalZones().Count(), inMods = ZonesInMods.Count;
        bool packs = inData == 0 && inMods == 0 ? inst?.Mode == "packs"
                   : inData == 0 ? true
                   : inMods == 0 ? false
                   : inst?.Mode == "packs" || inst?.Mode != "server" && inMods > inData;
        if (packs != PacksMode || !scanned)
            Log.Write(packs ? $"packs mode: {inMods} zones in mods, the game loads them itself"
                            : $"server mode: {inData} zones in the packs folder{(inMods > 0 ? $", {inMods} also in mods" : "")}");
        scanned = true;
        PacksMode = packs;
        // "Start Ticino" starts the server only in mode "server", the helper only in "packs"
        if (inst != null && inst.Mode != (packs ? "packs" : "server") && (inData > 0 || inMods > 0) && !Busy && !moving)
            Installer.SetMode(cfg, packs ? "packs" : "server", packs ? null : DataFolder);
        Raise(nameof(ZoneHome));
    }

    bool scanned;

    // ------------------------------------------------------------------------------------------- check
    /// <summary>Reads the release and sets every item's state. Call on the UI thread.</summary>
    public async Task Refresh()
    {
        if (Checking) return;
        Checking = true;
        Error = null;
        try
        {
            var rel = await Task.Run(() => gh.GetRelease(cfg.Repo, cfg.Tag, CancellationToken.None));
            await Task.Run(ScanMods);
            // the draft builds (ticino-all-cdae) carry the zones and the base only: the server program of their
            // branch is on the tools release (PC test of 1.1, 2026-11-01: "The server program is missing" for good)
            var assets = rel.Assets.ToList();
            string? serverFrom = null;
            if (!assets.Any(a => a.Name == ServerAsset) && cfg.UpdateServer && !PacksMode)
            {
                var (sa, from) = await Task.Run(() => ServerElsewhere(rel.Tag));
                if (sa != null) { assets.Add(sa); serverFrom = from; }
            }
            Release = rel;
            cfg.LastCheck = DateTime.Now;
            cfg.Save();
            var keepBusy = Items.Where(i => i.IsBusy || i.State == PackState.Queued).ToDictionary(i => i.Name);
            Items.Clear();
            foreach (var a in assets.OrderBy(a => a.Name.StartsWith("ticino_base") ? 0 : a.Name == ServerAsset ? 1 : 2)
                         .ThenBy(a => a.Name, StringComparer.OrdinalIgnoreCase))
            {
                PackItem? it = null;
                if (a.Name == ServerAsset)
                {
                    // packs mode runs no server; moving the zones out of mods (MoveZonesFromMods) gets it
                    if (cfg.UpdateServer && !PacksMode) it = new PackItem(a, PackKind.Server, "server") { From = serverFrom };
                }
                else if (a.Name.StartsWith("ticino_base_", StringComparison.OrdinalIgnoreCase) && a.Name.EndsWith(".zip"))
                    it = new PackItem(a, PackKind.Base, "base");
                else if (a.Name.StartsWith("ticino_", StringComparison.OrdinalIgnoreCase) && ZoneName().IsMatch(a.Name))
                    it = new PackItem(a, PackKind.Zone, ZoneOf(a.Name));
                if (it is null) continue;
                if (keepBusy.TryGetValue(it.Name, out var old)) it = old;
                Items.Add(it);
            }
            // a zone too big for one zip comes in pieces (ticino_ti_1_0_1.zip and _2.zip): both belong to it
            foreach (var g in Items.Where(i => i.Kind == PackKind.Zone).GroupBy(i => i.Zone, StringComparer.OrdinalIgnoreCase))
            {
                var parts = g.OrderBy(i => i.Name, StringComparer.OrdinalIgnoreCase).ToList();
                for (int k = 0; k < parts.Count; k++) parts[k].Part = parts.Count > 1 ? $"part {k + 1} of {parts.Count}" : null;
            }
            var items = Items.ToList();
            await Task.Run(() => Classify(items));
            UpdateSummary();
            Log.Write($"release {rel.Tag}: {Items.Count} zips, {InstalledZones} of {ReleaseZones} zones in place, " +
                      $"{NeedCount} to download or check ({Files.Size(NeedBytes)}){(PacksMode ? ", packs mode" : "")}");
            var need = Items.Where(i => i.NeedsDownload || i.State == PackState.Unchecked).ToList();
            if (need.Count is > 0 and <= 10)
                Log.Write("  " + string.Join(", ", need.Select(i => $"{i.Name} ({i.StateText})")));
        }
        catch (Exception e)
        {
            Error = e is HttpRequestException ? "GitHub cannot be reached: " + e.Message : e.Message;
            Log.Write("check failed: " + e.Message);
        }
        finally
        {
            Checking = false;
            UpdateSummary();
        }
    }

    /// <summary>Releases that carry the server program for a map release without one: the setting ServerTag, the
    /// tools release of the ticino branch (beamng/ticino/tools_release.txt), the public pre-release.</summary>
    static readonly string[] ToolReleases = { "ticino-all", "ticino-v1" };

    async Task<(ReleaseAsset?, string?)> ServerElsewhere(string tag)
    {
        foreach (var t in new[] { cfg.ServerTag }.Concat(ToolReleases).OfType<string>()
                     .Where(t => t.Length > 0 && t != tag).Distinct())
        {
            try
            {
                var r = await gh.GetRelease(cfg.Repo, t, CancellationToken.None);
                if (r.Assets.FirstOrDefault(x => x.Name == ServerAsset) is { } a)
                {
                    if (lastServerFrom != t) Log.Write($"release {tag} has no {ServerAsset}: the server program comes from {t}");
                    lastServerFrom = t;
                    return (a, t);
                }
            }
            catch (Exception e) { Log.Write($"{ServerAsset} not looked up in {t}: {e.Message}"); }
        }
        Log.Write($"no {ServerAsset} in {tag} nor in {string.Join(", ", ToolReleases)}");
        return (null, null);
    }

    string? lastServerFrom;

    /// <summary>The state of each item from the files on disk (no hashing: a zip in place but never checked is
    /// Unchecked and is hashed by <see cref="Verify"/>). Takes a copy of <see cref="Items"/> made on the UI thread
    /// (Refresh may rebuild the list meanwhile).</summary>
    void Classify(List<PackItem> items)
    {
        if (!Busy) LoadState();                             // a running download writes into the state it loaded
        ScanMods();
        var inst = InstallerChecked();
        var local = AllZones();
        var relNames = items.Select(i => i.Name).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var relZones = items.Where(i => i.Kind == PackKind.Zone).Select(i => i.Zone).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var it in items)
        {
            if (it.IsBusy || it.State == PackState.Queued) continue;
            it.Detail = "";
            it.Progress = 0;
            it.InPlace = false;
            string ready = ReadyPath(it);
            bool readyOk = File.Exists(ready) && new FileInfo(ready).Length == it.Size;
            if (it.Kind == PackKind.Server)
            {
                if (readyOk) { it.State = PackState.Ready; continue; }
                bool have = File.Exists(Path.Combine(ServerHome, Installer.ServerExeName));
                bool current = st.Server == $"{it.Name}|{it.Asset.Sha256}" && (st.ServerDir ?? OwnServerDir) == ServerHome
                               || Installer.Present(cfg) && it.Asset.Sha256 != null && StampOf(Installer.ServerStamp(cfg)) == it.Asset.Sha256;
                it.State = have && current ? PackState.Installed : have ? PackState.Update : PackState.Missing;
                continue;
            }
            string? dest = Dest(it);
            if (dest is null) { it.State = readyOk ? PackState.Ready : PackState.Missing; continue; }
            var f = new FileInfo(dest);
            it.InPlace = f.Exists && f.Length == it.Size;
            if (f.Exists && f.Length == it.Size)
            {
                string? sha = it.Asset.Sha256;
                if (sha is null) { it.State = PackState.Installed; continue; }
                string key = Key(sha, f);
                if (st.Checked.GetValueOrDefault(it.Name) == key || inst.GetValueOrDefault(it.Name) == key)
                {
                    it.State = PackState.Installed;
                    st.Checked[it.Name] = key;
                    // the zip in place IS the release's: a download of it left over (1.0.0 downloaded zips in place
                    // again) would replace it with itself and, with the old Install, retire its other piece
                    DropLeftovers(it);
                    continue;
                }
                // this very file was hashed before with another sha256: an older build under the same name
                else if (st.Checked.TryGetValue(it.Name, out var k) && !k.StartsWith(sha + "|") &&
                         k.EndsWith(key[sha.Length..]))
                    it.State = PackState.Update;
                else it.State = PackState.Unchecked;
            }
            else if (f.Exists) it.State = PackState.Update;
            // an older zip of the zone (a name the release no longer has); the other piece of a zone in two zips
            // (ticino_ti_1_0_1 and _2) is not one
            else if (it.Kind == PackKind.Zone && local.Any(l => ZoneOf(l.Name).Equals(it.Zone, StringComparison.OrdinalIgnoreCase)
                                                                 && !relNames.Contains(l.Name)))
                it.State = PackState.Update;
            else if (it.Kind == PackKind.Base && Directory.Exists(BeamNG.Mods(cfg)) &&
                     Directory.EnumerateFiles(BeamNG.Mods(cfg), "ticino_base_*.zip").Any())
                it.State = PackState.Update;
            else it.State = PackState.Missing;
            // a download finished and checked: it goes into place (unless the zip there is the release's, above)
            if (readyOk) it.State = PackState.Ready;
        }
        OldZips = local.Where(l => !relNames.Contains(l.Name) && relZones.Contains(ZoneOf(l.Name))).ToList();
        Raise(nameof(OldZips));
        if (!Busy && !moving) PruneOld(items);
        var places = PlaceNames(items);
        foreach (var it in items.Where(i => i.Kind == PackKind.Zone))
            it.Place = places.TryGetValue(it.Zone, out var p) ? p : null;
    }

    /// <summary>Removes the .ready / .part of a zip whose copy in place is the release's (40 GB of them were left in
    /// ticino_download\app on michi's PC).</summary>
    void DropLeftovers(PackItem it)
    {
        foreach (var p in new[] { ReadyPath(it), PartPath(it) })
            try
            {
                if (!File.Exists(p)) continue;
                File.Delete(p);
                Log.Write($"{Path.GetFileName(p)}: the zip in place is the release's, leftover download removed");
            }
            catch (Exception e) { Log.Write($"{p} not removed: {e.Message}"); }
    }

    /// <summary>Zone -> its biggest village, read from the spawn points in the base pack's info.json
    /// ("ti_1_3_spawn_bellinzona"). A zone's first three spawns are the route's (spawn_magliaso, _mid, _pura: the
    /// names of the Malcantone route, on the zone's main roads), then one per village by population.</summary>
    Dictionary<string, string> PlaceNames(List<PackItem> items)
    {
        var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            string mods = BeamNG.Mods(cfg);
            string? zip = Directory.Exists(mods)
                ? Directory.EnumerateFiles(mods, "ticino_base_*.zip").OrderByDescending(x => x).FirstOrDefault() : null;
            var baseItem = items.FirstOrDefault(i => i.Kind == PackKind.Base);
            if (zip is null && baseItem != null && ReadyPath(baseItem) is { } r && File.Exists(r)) zip = r;
            if (zip is null) return map;
            using var z = ZipFile.OpenRead(zip);
            var e = z.GetEntry("levels/ticino/info.json");
            if (e is null) return map;
            using var sr = new StreamReader(e.Open());
            var info = JsonNode.Parse(sr.ReadToEnd(), documentOptions: new JsonDocumentOptions { CommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true });
            var route = new HashSet<string> { "magliaso", "mid", "pura" };
            foreach (var sp in info?["spawnPoints"]?.AsArray() ?? new JsonArray())
            {
                string? n = sp?["objectname"]?.GetValue<string>();
                int k = n?.IndexOf("_spawn_", StringComparison.Ordinal) ?? -1;
                if (n is null || k < 0) continue;
                string zone = n[..k], slug = n[(k + 7)..];
                if (map.ContainsKey(zone) || route.Contains(slug)) continue;
                if (slug.EndsWith("_paese")) slug = slug[..^6];
                map[zone] = PlaceTitle(slug);
            }
        }
        catch (Exception ex) { Log.Write("place names: " + ex.Message); }
        return map;
    }

    /// <summary>"campione_d_italia" -> "Campione d'Italia", "roveredo_gr" -> "Roveredo (GR)". The spawn names are
    /// ASCII slugs of swissNAMES3D, which names Lugano in Romansh too (Ligiaun: the spawn took that one).</summary>
    public static string PlaceTitle(string slug)
    {
        if (slug == "ligiaun") return "Lugano";
        var w = slug.Split('_', StringSplitOptions.RemoveEmptyEntries).ToList();
        var o = new List<string>();
        for (int i = 0; i < w.Count; i++)
        {
            string x = w[i];
            string cap = char.ToUpper(x[0], Files.Culture) + x[1..];
            if (x == "d" && i + 1 < w.Count) { o.Add("d'" + char.ToUpper(w[i + 1][0], Files.Culture) + w[i + 1][1..]); i++; }
            else if (x == "s" && i == 0) o.Add("S.");
            else if (i == w.Count - 1 && i > 0 && x is ("gr" or "ur" or "vs" or "ti")) o.Add("(" + x.ToUpperInvariant() + ")");
            else o.Add(cap);
        }
        return string.Join(' ', o);
    }

    void UpdateSummary()
    {
        var need = Items.Where(i => i.NeedsDownload || i.State == PackState.Unchecked).ToList();
        NeedCount = need.Count;
        NeedBytes = need.Where(i => i.State != PackState.Unchecked).Sum(i => i.Size);
        ReadyCount = Items.Count(i => i.State == PackState.Ready);
        // zones, not zips (a zone may be two zips); a zip in place with the release's size counts while its sha256
        // waits to be checked (Verify), so a move or a new install does not show "0 of 87" for minutes
        var zones = Items.Where(i => i.Kind == PackKind.Zone).GroupBy(i => i.Zone, StringComparer.OrdinalIgnoreCase).ToList();
        ReleaseZones = zones.Count;
        InstalledZones = zones.Count(g => g.All(i => i.State is PackState.Installed or PackState.Unchecked or PackState.Verifying
                                                    || i.InPlace && i.State == PackState.Queued));
        UncheckedCount = Items.Count(i => i.State == PackState.Unchecked);
        if (Release is null) { Summary = Error ?? "Not checked yet."; return; }
        long total = Items.Where(i => i.Kind != PackKind.Server).Sum(i => i.Size);
        string s = $"{ReleaseZones} zones · {Files.Size(total)}";
        if (NeedCount == 0 && ReadyCount == 0) s += " · all up to date";
        else
        {
            int dl = NeedCount - UncheckedCount;
            if (dl > 0) s += $" · {dl} to download ({Files.Size(NeedBytes)})";
            if (UncheckedCount > 0) s += $" · {UncheckedCount} to check (sha256, no download)";
            if (ReadyCount > 0) s += $" · {ReadyCount} ready to install";
        }
        Summary = s;
    }

    // ------------------------------------------------------------------------------------------- download
    public void Pause() => cts?.Cancel();

    /// <summary>Checks the sha256 of the zips in place that were never checked (after a move to another disk without
    /// the installer's checked.json, or zips copied by hand): no download, unless one turns out different.</summary>
    public Task Verify()
    {
        if (Busy || Moving || UncheckedCount == 0) return Task.CompletedTask;
        Log.Write($"checking {UncheckedCount} zips in place (sha256)");
        return DownloadAll(i => i.State == PackState.Unchecked);
    }

    /// <summary>Checks, downloads and (when the server and the game are stopped) installs everything that is not
    /// up to date, or only the items <paramref name="only"/> picks. Call on the UI thread.</summary>
    public async Task DownloadAll(Func<PackItem, bool>? only = null)
    {
        if (Busy || Moving) return;
        var todo = Items.Where(i => (i.NeedsDownload || i.State == PackState.Unchecked) && (only is null || only(i))).ToList();
        // a zone to download needs its folder; checking zips in place, the base and the server do not
        if (ZoneHome is null && todo.Any(i => i.Kind == PackKind.Zone && i.State != PackState.Unchecked))
        {
            Error = "Choose the packs folder first.";
            return;
        }
        if (todo.Count == 0) { await ApplyPending(); return; }
        long need = todo.Where(i => i.State != PackState.Unchecked).Sum(i => i.Size - PartLength(i));
        string disk = ZoneHome ?? BeamNG.Mods(cfg);
        long free = Files.FreeSpace(disk);
        if (free > 0 && free < need + (2L << 30))
        {
            Error = $"Not enough space on {Path.GetPathRoot(disk)}: {Files.Size(free)} free, {Files.Size(need)} + 2 GB needed.";
            return;
        }
        Error = null;
        Busy = true;
        cts = new CancellationTokenSource();
        var ct = cts.Token;
        // the zips in place to check, known before every item shows "Queued": 1.0.0 looked at the state in One()
        // after it was set to Queued, so it never checked a zip in place and downloaded it again (52 GB on michi's
        // PC, 2026-10-31)
        var inPlace = todo.Where(i => i.State == PackState.Unchecked).ToHashSet();
        foreach (var it in todo) { it.State = PackState.Queued; it.Detail = ""; }
        Directory.CreateDirectory(DownloadDir);
        LoadState();
        long bytes = todo.Where(i => !inPlace.Contains(i)).Sum(i => i.Size);
        var meter = new Meter(bytes);
        foreach (var it in todo) meter.Add(PartLength(it));
        try
        {
            using var gate = new SemaphoreSlim(Math.Clamp(cfg.ParallelDownloads, 1, 6));
            var tasks = todo.Select(async it =>
            {
                await gate.WaitAsync(ct);
                try { await Task.Run(() => One(it, inPlace.Contains(it), meter, ct), ct); }
                catch (OperationCanceledException) { throw; }
                catch (Exception e)
                {
                    it.State = PackState.Error;
                    it.Detail = e.Message;
                    Log.Write($"{it.Name}: {e.Message}");
                }
                finally { gate.Release(); }
            }).ToList();
            _ = Task.Run(async () =>
            {
                while (!ct.IsCancellationRequested && tasks.Any(t => !t.IsCompleted))
                {
                    if (bytes == 0)
                    {
                        // only zips in place to check: no bytes to count, zips instead
                        int done = todo.Count(i => i.State is not (PackState.Queued or PackState.Verifying));
                        Overall = 100.0 * done / todo.Count;
                        ProgressText = $"Checking the zips in place (sha256, no download): {done} of {todo.Count}";
                    }
                    else
                    {
                        Overall = meter.Fraction * 100;
                        ProgressText = meter.Text();
                    }
                    await Task.Delay(500);
                }
            });
            try { await Task.WhenAll(tasks); }
            catch (OperationCanceledException) { }
            Overall = bytes == 0 ? 100 : meter.Fraction * 100;
            ProgressText = ct.IsCancellationRequested ? "Paused: it resumes where it stopped." : "";
        }
        finally
        {
            foreach (var it in todo.Where(i => i.State is PackState.Queued or PackState.Downloading or PackState.Verifying))
            {
                it.State = inPlace.Contains(it) && Dest(it) is { } d && File.Exists(d) ? PackState.Unchecked
                         : PartLength(it) > 0 ? PackState.Update : PackState.Missing;
                it.Detail = "";
            }
            SaveState();
            Busy = false;
            UpdateSummary();
        }
        if (!ct.IsCancellationRequested) await ApplyPending();
    }

    long PartLength(PackItem it)
    {
        string? p = PartPath(it);
        return p != null && File.Exists(p) ? new FileInfo(p).Length : 0;
    }

    sealed class Meter
    {
        long total, done, lastDone;
        readonly Stopwatch sw = Stopwatch.StartNew();
        double lastT, speed;
        public Meter(long total) { this.total = Math.Max(1, total); }
        public void Add(long n) => Interlocked.Add(ref done, n);
        public double Fraction => Math.Clamp((double)Interlocked.Read(ref done) / total, 0, 1);
        public string Text()
        {
            double t = sw.Elapsed.TotalSeconds;
            long d = Interlocked.Read(ref done);
            if (t - lastT >= 1)
            {
                double s = (d - lastDone) / (t - lastT);
                speed = speed <= 0 ? s : speed * 0.7 + s * 0.3;
                lastT = t;
                lastDone = d;
            }
            string text = $"{Files.Size(d)} of {Files.Size(total)}";
            if (speed > 1000)
                text += $" · {Files.Speed(speed)} · {Files.Duration(TimeSpan.FromSeconds((total - d) / speed))} left";
            return text;
        }
    }

    async Task One(PackItem it, bool inPlace, Meter meter, CancellationToken ct)
    {
        string? sha = it.Asset.Sha256;
        if (inPlace)
        {
            string dest = Dest(it)!;
            it.State = PackState.Verifying;
            string h = await Hash(dest, it, ct);
            if (h == sha)
            {
                lock (st) st.Checked[it.Name] = Key(sha!, new FileInfo(dest));
                it.State = PackState.Installed;
                DropLeftovers(it);
                Log.Write($"{it.Name}: in place and checked");
                return;
            }
            Log.Write($"{it.Name}: the zip in place has another sha256: downloaded again");
            meter.Add(0);
        }
        string part = PartPath(it), ready = ReadyPath(it);
        bool fetched = false;
        for (int attempt = 1; attempt <= 6; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            long have = File.Exists(part) ? new FileInfo(part).Length : 0;
            if (have > it.Size) { File.Delete(part); meter.Add(-have); have = 0; }
            if (have < it.Size)
            {
                it.State = PackState.Downloading;
                try
                {
                    using var r = await gh.OpenAsset(it.Asset, have, ct);
                    if (have > 0 && r.StatusCode != HttpStatusCode.PartialContent) { meter.Add(-have); have = 0; }
                    await using var src = await r.Content.ReadAsStreamAsync(ct);
                    await using var dst = new FileStream(part, have > 0 ? FileMode.Append : FileMode.Create,
                        FileAccess.Write, FileShare.None, 1 << 20, true);
                    var buf = new byte[1 << 20];
                    var last = Stopwatch.StartNew();
                    int n;
                    while ((n = await src.ReadAsync(buf, ct)) > 0)
                    {
                        await dst.WriteAsync(buf.AsMemory(0, n), ct);
                        fetched = true;
                        have += n;
                        meter.Add(n);
                        if (last.ElapsedMilliseconds > 250)
                        {
                            it.Progress = 100.0 * have / it.Size;
                            it.Detail = $"{Files.Size(have)} of {Files.Size(it.Size)}";
                            last.Restart();
                        }
                    }
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception e)
                {
                    if (e.Message == "range" && File.Exists(part))
                    {
                        meter.Add(-new FileInfo(part).Length);
                        File.Delete(part);
                    }
                    it.Detail = $"attempt {attempt}/6: {e.Message}";
                    Log.Write($"{it.Name}: {e.Message} (try {attempt})");
                    await Task.Delay(TimeSpan.FromSeconds(10 * attempt), ct);
                    await Renew(it, ct);
                    continue;
                }
                have = new FileInfo(part).Length;
            }
            if (have != it.Size) { it.Detail = $"size {have} instead of {it.Size}"; continue; }
            if (sha != null)
            {
                it.State = PackState.Verifying;
                string h = await Hash(part, it, ct);
                if (h != sha)
                {
                    Log.Write($"{it.Name}: wrong sha256, downloaded again");
                    meter.Add(-have);
                    File.Delete(part);
                    continue;
                }
            }
            File.Move(part, ready, true);
            it.Progress = 100;
            it.Detail = "";
            it.State = PackState.Ready;
            Log.Write(fetched ? $"{it.Name}: downloaded and checked" : $"{it.Name}: checked (its download had finished before)");
            return;
        }
        it.State = PackState.Error;
        if (it.Detail.Length == 0) it.Detail = "download failed";
    }

    /// <summary>A workflow can replace an asset while we download (new id: the old one answers 404).</summary>
    async Task Renew(PackItem it, CancellationToken ct)
    {
        try
        {
            var rel = await gh.GetRelease(cfg.Repo, cfg.Tag, ct);
            var a = rel.Assets.FirstOrDefault(x => x.Name == it.Name);
            if (a is null || a.Id == it.Asset.Id) return;
            Log.Write($"{it.Name} was replaced on the release");
            if (a.Size != it.Asset.Size || a.Sha256 != it.Asset.Sha256)
            {
                string? p = PartPath(it);
                if (p != null && File.Exists(p)) File.Delete(p);
            }
            it.Asset = a;
        }
        catch { /* try the old one again */ }
    }

    static async Task<string> Hash(string path, PackItem it, CancellationToken ct)
    {
        using var h = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        await using var f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 22, true);
        var buf = new byte[1 << 22];
        long done = 0, len = Math.Max(1, f.Length);
        int n;
        while ((n = await f.ReadAsync(buf, ct)) > 0)
        {
            h.AppendData(buf, 0, n);
            done += n;
            it.Progress = 100.0 * done / len;
        }
        return Convert.ToHexString(h.GetHashAndReset()).ToLowerInvariant();
    }

    // ------------------------------------------------------------------------------------------- install
    /// <summary>Why the downloaded zips cannot go into place now, or null.</summary>
    public string? ApplyBlocker()
    {
        if (BeamNG.Running()) return GameOpenReason;
        if (ServerRunning()) return ServerRunningReason;
        return null;
    }

    /// <summary>Puts every downloaded zip into place (when nothing keeps them open) and removes the old ones.
    /// Returns the number installed.</summary>
    public async Task<int> ApplyPending()
    {
        if (applying) return 0;                             // called from several places: one install at a time
        var ready = Items.Where(i => i.State == PackState.Ready).ToList();
        if (ready.Count == 0 && OldZips.Count == 0) return 0;
        string? why = ApplyBlocker();
        if (why != null)
        {
            if (ready.Count > 0) Log.Write($"{ready.Count} zips ready, installed when {why} no longer");
            UpdateSummary();
            return 0;
        }
        applying = true;
        try { return await Apply(ready); }
        finally { applying = false; }
    }

    bool applying;

    async Task<int> Apply(List<PackItem> ready)
    {
        int n = 0;
        await Task.Run(() =>
        {
            LoadState();
            foreach (var it in ready)
            {
                try
                {
                    Install(it);
                    n++;
                }
                catch (Exception e)
                {
                    it.State = PackState.Error;
                    it.Detail = "install: " + e.Message;
                    Log.Write($"{it.Name}: not installed ({e.Message})");
                }
            }
            RemoveOld();
            SaveState();
        });
        await Reclassify();
        UpdateSummary();
        if (n > 0) { Log.Write($"{n} zips installed"); Applied?.Invoke(); }
        return n;
    }

    void Install(PackItem it)
    {
        string ready = ReadyPath(it)!;
        string? sha = it.Asset.Sha256;
        switch (it.Kind)
        {
            case PackKind.Server:
            {
                // only the exe: the zip's lua folder is the server's test override, which would hide the base pack's
                string home = ServerHome, exe = Path.Combine(home, Installer.ServerExeName);
                Directory.CreateDirectory(home);
                using (var z = ZipFile.OpenRead(ready))
                {
                    var e = z.Entries.FirstOrDefault(x => x.Name.Equals(Installer.ServerExeName, StringComparison.OrdinalIgnoreCase))
                            ?? throw new InvalidDataException($"no {Installer.ServerExeName} in {it.Name}");
                    e.ExtractToFile(exe + ".new", true);
                }
                File.Move(exe + ".new", exe, true);
                File.Delete(ready);
                if (Installer.Present(cfg) && sha != null) File.WriteAllText(Installer.ServerStamp(cfg), sha);
                st.Server = $"{it.Name}|{sha}";
                st.ServerDir = home;
                Log.Write($"server installed in {home}");
                break;
            }
            case PackKind.Base:
            {
                string mods = BeamNG.Mods(cfg);
                Directory.CreateDirectory(mods);
                foreach (var old in Directory.EnumerateFiles(mods, "ticino_base_*.zip"))
                    if (!Path.GetFileName(old).Equals(it.Name, StringComparison.OrdinalIgnoreCase)) Retire(old);
                string dest = Path.Combine(mods, it.Name);
                File.Move(ready, dest, true);
                if (sha != null) st.Checked[it.Name] = Key(sha, new FileInfo(dest));
                string tag = $"{it.Name}|{sha}";
                if (st.Base != tag)
                {
                    // a new base: the game's cache of the level would mix old and new (install_ticino.ps1)
                    string cache = BeamNG.LevelCache(cfg);
                    if (Directory.Exists(cache)) { Directory.Delete(cache, true); Log.Write("level cache cleared"); }
                    st.Base = tag;
                }
                EnableMods();
                break;
            }
            default:
            {
                string dest = Target(it) ?? throw new InvalidOperationException("no packs folder");
                Directory.CreateDirectory(ZoneHome!);
                // a copy of this zip in the other folder: one copy only (older zips of the zone, names the release no
                // longer has, go in RemoveOld; the other piece of a zone in two zips is NOT an old one: 1.0.0 moved
                // ticino_ti_1_0_1.zip to "old" when it installed _2 and downloaded it again, PC test 2026-10-31)
                foreach (var old in AllZones().Where(l => l.Name.Equals(it.Name, StringComparison.OrdinalIgnoreCase)
                                                          && !l.FullName.Equals(Path.GetFullPath(dest), StringComparison.OrdinalIgnoreCase)))
                    Retire(old.FullName);
                File.Move(ready, dest, true);
                if (sha != null) st.Checked[it.Name] = Key(sha, new FileInfo(dest));
                break;
            }
        }
        it.State = PackState.Installed;
    }

    void RemoveOld()
    {
        foreach (var f in OldZips) Retire(f.FullName);
    }

    /// <summary>An old zip: deleted (setting "Delete old packs"), or moved to the packs folder's "old" (in packs mode
    /// the installer's ticino_download\old, on the disk of mods).</summary>
    void Retire(string path, bool forget = true)
    {
        try
        {
            if (!File.Exists(path)) return;
            if (cfg.DeleteOld)
            {
                File.Delete(path);
                Log.Write("deleted " + path);
            }
            else
            {
                string dir = OldDir(path);
                Directory.CreateDirectory(dir);
                File.Move(path, Path.Combine(dir, Path.GetFileName(path)), true);
                Log.Write($"moved {path} to {dir}");
            }
            // forget: false for a second copy of a zip that stays (its name is the one kept in place)
            if (forget) st.Checked.Remove(Path.GetFileName(path));
        }
        catch (Exception e) { Log.Write($"could not remove {path}: {e.Message}"); }
    }

    /// <summary>Deletes the zips in the "old" folders that are copies of a zip in place: same name and size as a
    /// release zip whose copy in place is checked (put aside by a move or an install, not an older build, which has
    /// another name or size). 1.0.0 and 1.1 left about 50 GB of them in ticino_download\old (PC test 2026-11-01).</summary>
    void PruneOld(List<PackItem> items)
    {
        var ok = items.Where(i => i.State == PackState.Installed && i.Asset.Sha256 != null && i.Kind != PackKind.Server)
                      .ToDictionary(i => i.Name, i => i.Size, StringComparer.OrdinalIgnoreCase);
        int n = 0;
        long freed = 0;
        var dirs = new[] { Path.Combine(Work, "old"), DataFolder is null ? null : Path.Combine(DataFolder, "old") };
        foreach (var dir in dirs.OfType<string>().Distinct(StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                if (!Directory.Exists(dir)) continue;
                foreach (var f in new DirectoryInfo(dir).EnumerateFiles("ticino_*.zip"))
                {
                    if (!ok.TryGetValue(f.Name, out long size) || f.Length != size) continue;
                    try
                    {
                        f.Delete();
                        n++;
                        freed += size;
                    }
                    catch (Exception e) { Log.Write($"could not delete {f.FullName}: {e.Message}"); }
                }
            }
            catch (Exception e) { Log.Write($"{dir} not read: {e.Message}"); }
        }
        if (n > 0) Log.Write($"{n} copies of zips in place deleted from the old folders ({Files.Size(freed)} freed)");
    }

    /// <summary>The "old" folder on the zip's own disk (moving it there is a rename): the packs folder's for a zip in
    /// the packs folder, the installer's ticino_download\old (beside mods) for every other.</summary>
    string OldDir(string path)
    {
        string? dir = Path.GetDirectoryName(Path.GetFullPath(path));
        if (DataFolder != null && dir != null && dir.Equals(Path.GetFullPath(DataFolder).TrimEnd('\\', '/'), StringComparison.OrdinalIgnoreCase))
            return Path.Combine(DataFolder, "old");
        return Path.Combine(Work, "old");
    }

    /// <summary>After a game update BeamNG turns every mod off in mods\db.json: the Ticino ones go back on.</summary>
    void EnableMods()
    {
        string db = Path.Combine(BeamNG.Mods(cfg), "db.json");
        try
        {
            if (!File.Exists(db) || JsonNode.Parse(File.ReadAllText(db)) is not JsonObject root) return;
            if (root["mods"] is not JsonObject mods) return;
            int changed = 0;
            foreach (var (name, node) in mods)
                if (name.StartsWith("ticino_") && node is JsonObject m && m["active"] is JsonValue v &&
                    v.TryGetValue(out bool on) && !on)
                {
                    m["active"] = true;
                    changed++;
                }
            if (changed == 0) return;
            Directory.CreateDirectory(DownloadDir);
            File.Copy(db, Path.Combine(DownloadDir, "db.json.bak"), true);
            Files.WriteAtomic(db, root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
            Log.Write($"{changed} Ticino mods turned back on in mods\\db.json");
        }
        catch (Exception e) { Log.Write("mods\\db.json not read: " + e.Message); }
    }

    // ------------------------------------------------------------------------------------------- moving packs
    async Task Reclassify()
    {
        var items = Items.ToList();
        await Task.Run(() => Classify(items));
    }

    /// <summary>A zip that is moved keeps the sha256 it was checked with (state.json, the installer's checked.json):
    /// its key is written again for the new file (another disk may keep the times coarser).</summary>
    void Rekey(string name, long length, long ticks, FileInfo moved, Dictionary<string, string> inst)
    {
        string tail = $"|{length}|{ticks}";
        string? k = st.Checked.GetValueOrDefault(name);
        if (k is null || !k.EndsWith(tail)) k = inst.GetValueOrDefault(name);
        if (k is null || !k.EndsWith(tail)) return;
        moved.Refresh();
        st.Checked[name] = $"{k[..^tail.Length]}|{moved.Length}|{moved.LastWriteTimeUtc.Ticks}";
    }

    /// <summary>Moves zips into a folder, one after the other, with <see cref="MoveText"/> saying how far (the pages
    /// show it: 1.0.0 wrote it into a bar the page's own refresh overwrote every second, and a 10 min copy from C:
    /// to D: looked like a hang). A zip that the folder already has with the same size is not copied again: that
    /// copy goes to the "old" folder on its own disk. Returns the zips that could not be moved.</summary>
    async Task<List<string>> MoveInto(List<FileInfo> files, string to, Func<FileInfo, string> rel)
    {
        var inst = InstallerChecked();
        var shas = Items.Where(i => i.Asset.Sha256 != null).GroupBy(i => i.Name, StringComparer.OrdinalIgnoreCase)
                        .ToDictionary(g => g.Key, g => g.First().Asset.Sha256!, StringComparer.OrdinalIgnoreCase);
        var failed = new List<string>();
        long total = files.Sum(f => f.Length), done = 0;
        var sw = Stopwatch.StartNew();
        int n = 0;
        Moving = true;
        try
        {
            LoadState();
            foreach (var f in files)
            {
                n++;
                string dst = Path.Combine(to, rel(f));
                long length = f.Length, ticks = f.LastWriteTimeUtc.Ticks;
                void Show(long extra)
                {
                    double t = sw.Elapsed.TotalSeconds, d = done + extra;
                    string left = t > 5 && d > 0 && d < total ? $" · {Files.Duration(TimeSpan.FromSeconds(t * (total - d) / d))} left" : "";
                    MoveText = $"{f.Name} ({n} of {files.Count}) · {Files.Size(d)} of {Files.Size(total)}{left}";
                }
                Show(0);
                try
                {
                    if (File.Exists(dst) && new FileInfo(dst).Length == length &&
                        !Path.GetFullPath(dst).Equals(f.FullName, StringComparison.OrdinalIgnoreCase))
                    {
                        if (shas.ContainsKey(f.Name))
                        {
                            // a zip of the release: the copy there stays (Check hashes it, and downloads it again
                            // should it not be the release's); a second copy put aside was 50 GB on C: (2026-11-01)
                            File.Delete(f.FullName);
                            Log.Write($"{f.Name}: already in {to} with the same size, the other copy deleted");
                        }
                        else
                        {
                            Retire(f.FullName, forget: false);
                            Log.Write($"{f.Name}: already in {to} with the same size, the other copy put aside");
                        }
                    }
                    else
                    {
                        long copied = 0, shown = 0;
                        await Task.Run(() => Files.MoveAsync(f.FullName, dst, new SyncProgress(b =>
                        {
                            copied += b;
                            if (copied - shown > 64 << 20) { shown = copied; Show(copied); }
                        }), CancellationToken.None));
                        Rekey(f.Name, length, ticks, new FileInfo(dst), inst);
                        Log.Write($"moved {f.Name} to {to}");
                    }
                }
                catch (Exception e)
                {
                    failed.Add(f.Name);
                    Log.Write($"{f.Name} not moved: {e.Message}");
                }
                done += length;
            }
            SaveState();
        }
        finally
        {
            Moving = false;
            MoveText = "";
        }
        return failed;
    }

    /// <summary>A progress that reports on the thread that copies (Progress&lt;T&gt; posts to the UI thread, which
    /// read the counter long after the copy).</summary>
    sealed class SyncProgress(Action<long> on) : IProgress<long>
    {
        public void Report(long value) => on(value);
    }

    /// <summary>Moves the zone zips from mods into the packs folder (on one drive a rename): packs mode becomes server
    /// mode, also for "Start Ticino" (install.json "mode": "server"). Throws with the zips that could not be moved.</summary>
    public async Task MoveZonesFromMods()
    {
        if (DataFolder is null) throw new InvalidOperationException("Choose the packs folder first.");
        if (Busy || Moving) throw new InvalidOperationException("Wait for the download to end (or pause it) first.");
        if (BeamNG.Running()) throw new InvalidOperationException("Close BeamNG: it keeps the zips in mods open.");
        if (BaseHasServerLua() == false)
            throw new InvalidOperationException("The base pack in mods loads zones from mods only: the server could not serve them. Update it first (Downloads page).");
        ScanMods();
        var list = ZonesInMods.ToList();
        Directory.CreateDirectory(DataFolder);
        var failed = await MoveInto(list, DataFolder, f => f.Name);
        Installer.SetMode(cfg, "server", DataFolder);
        await Reclassify();
        UpdateSummary();
        if (failed.Count > 0)
            throw new IOException($"{failed.Count} of {list.Count} zips could not be moved (in use?): {string.Join(", ", failed.Take(5))}" +
                                  (failed.Count > 5 ? ", …" : "") + ". Close BeamNG and the Ticino tools and press Move again.");
    }

    /// <summary>A new data folder: the zips (and the unfinished downloads) of the old one go with it.</summary>
    public async Task ChangeDataFolder(string? from, string to, bool move)
    {
        if (Busy || Moving) throw new InvalidOperationException("Wait for the download to end (or pause it) first.");
        var failed = new List<string>();
        if (move && from != null && Directory.Exists(from) && !Path.GetFullPath(from).Equals(Path.GetFullPath(to), StringComparison.OrdinalIgnoreCase))
        {
            if (ServerRunning()) throw new InvalidOperationException("Stop the server before moving the packs.");
            var files = new DirectoryInfo(from).EnumerateFiles("ticino_*.zip").ToList();
            string dl = Path.Combine(from, ".download");
            if (Directory.Exists(dl)) files.AddRange(new DirectoryInfo(dl).EnumerateFiles());
            failed = await MoveInto(files, to, f => Path.GetRelativePath(from, f.FullName));
            Log.Write($"{files.Count - failed.Count} files moved from {from} to {to}");
        }
        cfg.DataFolder = to;
        cfg.Save();
        Directory.CreateDirectory(to);
        Raise(nameof(DataFolder));
        await Reclassify();
        UpdateSummary();
        if (failed.Count > 0)
            throw new IOException($"{failed.Count} files stayed in {from} (in use?): {string.Join(", ", failed.Take(5))}");
    }

    /// <summary>&lt;user&gt;\ticino_data as the installer (on the disk of mods: moving the zips there is a rename) when
    /// that disk has room for the map or already holds it, else the disk with the most free space.</summary>
    public string SuggestDataFolder()
    {
        string user = Path.Combine(BeamNG.UserFolder(cfg), "ticino_data");
        long need = Math.Max(0, (Release?.Assets.Where(a => ZoneName().IsMatch(a.Name) && !a.Name.StartsWith("ticino_base")).Sum(a => a.Size) ?? 56_000_000_000L)
                                - ZonesInMods.Sum(z => z.Length));
        if (Installer.DataFolder(cfg) is { } inst) return inst;
        if (Files.FreeSpace(BeamNG.UserFolder(cfg)) > need + 2_000_000_000L) return user;
        var best = DriveInfo.GetDrives()
            .Where(d => d.DriveType == DriveType.Fixed && d.IsReady)
            .OrderByDescending(d => d.AvailableFreeSpace)
            .FirstOrDefault();
        return best is null
            ? Path.Combine(AppConfig.Dir, "data")
            : Path.Combine(best.RootDirectory.FullName, "TicinoData");
    }

    /// <summary>Does the base pack in mods carry the server's Lua (ticino/files.lua)? null: no base installed.</summary>
    public bool? BaseHasServerLua()
    {
        try
        {
            string mods = BeamNG.Mods(cfg);
            if (!Directory.Exists(mods)) return null;
            string? b = Directory.EnumerateFiles(mods, "ticino_base_*.zip").OrderByDescending(x => x).FirstOrDefault();
            if (b is null) return null;
            using var z = ZipFile.OpenRead(b);
            return z.GetEntry("lua/ge/extensions/ticino/files.lua") != null;
        }
        catch { return null; }
    }
}
