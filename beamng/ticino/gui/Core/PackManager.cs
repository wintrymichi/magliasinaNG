using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace TicinoServer.Core;

/// <summary>The zips of a Ticino release on GitHub against what is on this PC: the zone packs in the data folder,
/// the base pack in BeamNG's mods, the server program in %LOCALAPPDATA%\TicinoServer\server. Downloads resume
/// (data\.download\name.part), every zip is checked by the sha256 GitHub keeps for it, and a downloaded zip
/// (name.ready) goes into place only while the server and the game are not running (they keep the zips open).
/// Same rules as install_ticino.ps1: a zip whose zone the release has under another name is old; a zone the
/// release has no zip of at all is kept.</summary>
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

    public bool CanDownload => !Busy && NeedCount > 0;

    /// <summary>Zone zips in BeamNG's mods (an install made without the server): the game mounts every one of them
    /// at each start (75-81 s), and with the server they belong in the data folder.</summary>
    public List<FileInfo> ZonesInMods { get; private set; } = new();

    /// <summary>Old zips of this PC: zones the release has under another name.</summary>
    public List<FileInfo> OldZips { get; private set; } = new();

    public string? DataFolder => string.IsNullOrWhiteSpace(cfg.DataFolder) ? null : cfg.DataFolder;
    string? DownloadDir => DataFolder is null ? null : Path.Combine(DataFolder, ".download");
    public static string ServerDir => Path.Combine(AppConfig.Dir, "server");

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
    }

    string StatePath => Path.Combine(DownloadDir ?? Path.Combine(AppConfig.Dir, "download"), "state.json");

    void LoadState()
    {
        try
        {
            st = File.Exists(StatePath) ? JsonSerializer.Deserialize<State>(File.ReadAllText(StatePath)) ?? new() : new();
        }
        catch { st = new(); }
    }

    void SaveState()
    {
        try { Files.WriteAtomic(StatePath, JsonSerializer.Serialize(st, new JsonSerializerOptions { WriteIndented = true })); }
        catch (Exception e) { Log.Write("state.json not written: " + e.Message); }
    }

    static string Key(string sha, FileInfo f) => $"{sha}|{f.Length}|{f.LastWriteTimeUtc.Ticks}";

    // ------------------------------------------------------------------------------------------- where things go
    string? Dest(PackItem it) => it.Kind switch
    {
        PackKind.Base => Path.Combine(BeamNG.Mods(cfg), it.Name),
        PackKind.Zone => DataFolder is null ? null : Path.Combine(DataFolder, it.Name),
        _ => null,
    };

    string? ReadyPath(PackItem it) => DownloadDir is null ? null : Path.Combine(DownloadDir, it.Name + ".ready");
    string? PartPath(PackItem it) => DownloadDir is null ? null : Path.Combine(DownloadDir, it.Name + ".part");

    public static string? ServerExe()
    {
        string beside = Path.Combine(AppContext.BaseDirectory, "ticino_server.exe");
        if (File.Exists(beside)) return beside;
        string p = Path.Combine(ServerDir, "ticino_server.exe");
        return File.Exists(p) ? p : null;
    }

    IEnumerable<FileInfo> LocalZones()
    {
        if (DataFolder is null || !Directory.Exists(DataFolder)) return Array.Empty<FileInfo>();
        return new DirectoryInfo(DataFolder).EnumerateFiles("ticino_*.zip")
            .Where(f => !f.Name.StartsWith("ticino_base", StringComparison.OrdinalIgnoreCase));
    }

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
            Release = rel;
            cfg.LastCheck = DateTime.Now;
            cfg.Save();
            var keepBusy = Items.Where(i => i.IsBusy || i.State == PackState.Queued).ToDictionary(i => i.Name);
            Items.Clear();
            foreach (var a in rel.Assets.OrderBy(a => a.Name.StartsWith("ticino_base") ? 0 : a.Name == ServerAsset ? 1 : 2)
                         .ThenBy(a => a.Name, StringComparer.OrdinalIgnoreCase))
            {
                PackItem? it = null;
                if (a.Name == ServerAsset)
                {
                    if (cfg.UpdateServer) it = new PackItem(a, PackKind.Server, "server");
                }
                else if (a.Name.StartsWith("ticino_base_", StringComparison.OrdinalIgnoreCase) && a.Name.EndsWith(".zip"))
                    it = new PackItem(a, PackKind.Base, "base");
                else if (a.Name.StartsWith("ticino_", StringComparison.OrdinalIgnoreCase) && ZoneName().IsMatch(a.Name))
                    it = new PackItem(a, PackKind.Zone, ZoneOf(a.Name));
                if (it is null) continue;
                if (keepBusy.TryGetValue(it.Name, out var old)) it = old;
                Items.Add(it);
            }
            await Task.Run(Classify);
            Log.Write($"release {rel.Tag}: {Items.Count} zip, {NeedCount} da scaricare ({Files.Size(NeedBytes)})");
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

    /// <summary>The state of each item from the files on disk (no hashing: a zip in place but never checked is
    /// Unchecked and is hashed by the download job).</summary>
    void Classify()
    {
        LoadState();
        var local = LocalZones().ToList();
        var relNames = Items.Select(i => i.Name).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var relZones = Items.Where(i => i.Kind == PackKind.Zone).Select(i => i.Zone).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var it in Items)
        {
            if (it.IsBusy || it.State == PackState.Queued) continue;
            it.Detail = "";
            it.Progress = 0;
            string? ready = ReadyPath(it);
            if (ready != null && File.Exists(ready) && new FileInfo(ready).Length == it.Size)
            {
                it.State = PackState.Ready;
                continue;
            }
            if (it.Kind == PackKind.Server)
            {
                bool have = ServerExe() != null;
                it.State = have && st.Server == $"{it.Name}|{it.Asset.Sha256}" ? PackState.Installed
                    : have ? PackState.Update : PackState.Missing;
                continue;
            }
            string? dest = Dest(it);
            if (dest is null) { it.State = PackState.Missing; continue; }
            var f = new FileInfo(dest);
            if (f.Exists && f.Length == it.Size)
            {
                string? sha = it.Asset.Sha256;
                if (sha is null) it.State = PackState.Installed;
                else if (st.Checked.TryGetValue(it.Name, out var k))
                    it.State = k == Key(sha, f) ? PackState.Installed
                        : k.StartsWith(sha + "|") ? PackState.Unchecked : PackState.Update;
                else it.State = PackState.Unchecked;
            }
            else if (f.Exists) it.State = PackState.Update;
            else if (it.Kind == PackKind.Zone && local.Any(l => ZoneOf(l.Name).Equals(it.Zone, StringComparison.OrdinalIgnoreCase)))
                it.State = PackState.Update;
            else if (it.Kind == PackKind.Base && Directory.Exists(BeamNG.Mods(cfg)) &&
                     Directory.EnumerateFiles(BeamNG.Mods(cfg), "ticino_base_*.zip").Any())
                it.State = PackState.Update;
            else it.State = PackState.Missing;
        }
        OldZips = local.Where(l => !relNames.Contains(l.Name) && relZones.Contains(ZoneOf(l.Name))).ToList();
        try
        {
            ZonesInMods = Directory.Exists(BeamNG.Mods(cfg))
                ? new DirectoryInfo(BeamNG.Mods(cfg)).EnumerateFiles("ticino_*.zip", SearchOption.AllDirectories)
                    .Where(z => !z.Name.StartsWith("ticino_base", StringComparison.OrdinalIgnoreCase)).ToList()
                : new();
        }
        catch { ZonesInMods = new(); }
        Raise(nameof(ZonesInMods));
        Raise(nameof(OldZips));
        var places = PlaceNames();
        foreach (var it in Items.Where(i => i.Kind == PackKind.Zone))
            it.Place = places.TryGetValue(it.Zone, out var p) ? p : null;
    }

    /// <summary>Zone -> its biggest village, read from the spawn points in the base pack's info.json
    /// ("ti_1_3_spawn_bellinzona"). A zone's first three spawns are the route's (spawn_magliaso, _mid, _pura: the
    /// names of the Malcantone route, on the zone's main roads), then one per village by population.</summary>
    Dictionary<string, string> PlaceNames()
    {
        var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            string mods = BeamNG.Mods(cfg);
            string? zip = Directory.Exists(mods)
                ? Directory.EnumerateFiles(mods, "ticino_base_*.zip").OrderByDescending(x => x).FirstOrDefault() : null;
            var baseItem = Items.FirstOrDefault(i => i.Kind == PackKind.Base);
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
        ReleaseZones = Items.Count(i => i.Kind == PackKind.Zone);
        InstalledZones = Items.Count(i => i.Kind == PackKind.Zone && i.State == PackState.Installed);
        if (Release is null) { Summary = Error ?? "Not checked yet."; return; }
        long total = Items.Where(i => i.Kind != PackKind.Server).Sum(i => i.Size);
        string s = $"{ReleaseZones} zones · {Files.Size(total)}";
        if (NeedCount == 0 && ReadyCount == 0) s += " · all up to date";
        else
        {
            if (NeedCount > 0) s += $" · {NeedCount} to download ({Files.Size(NeedBytes)})";
            if (ReadyCount > 0) s += $" · {ReadyCount} ready to install";
        }
        Summary = s;
    }

    // ------------------------------------------------------------------------------------------- download
    public void Pause() => cts?.Cancel();

    /// <summary>Checks, downloads and (when the server and the game are stopped) installs everything that is not
    /// up to date. Call on the UI thread.</summary>
    public async Task DownloadAll()
    {
        if (Busy) return;
        if (DataFolder is null)
        {
            Error = "Choose the packs folder first.";
            return;
        }
        var todo = Items.Where(i => i.NeedsDownload || i.State == PackState.Unchecked).ToList();
        if (todo.Count == 0) { await ApplyPending(); return; }
        long need = todo.Where(i => i.State != PackState.Unchecked).Sum(i => i.Size - PartLength(i));
        long free = Files.FreeSpace(DataFolder);
        if (free > 0 && free < need + (2L << 30))
        {
            Error = $"Not enough space on {Path.GetPathRoot(DataFolder)}: {Files.Size(free)} free, {Files.Size(need)} + 2 GB needed.";
            return;
        }
        Error = null;
        Busy = true;
        cts = new CancellationTokenSource();
        var ct = cts.Token;
        foreach (var it in todo) { it.State = PackState.Queued; it.Detail = ""; }
        Directory.CreateDirectory(DownloadDir!);
        LoadState();
        var meter = new Meter(todo.Where(i => i.State != PackState.Unchecked).Sum(i => i.Size));
        foreach (var it in todo) meter.Add(PartLength(it));
        try
        {
            using var gate = new SemaphoreSlim(Math.Clamp(cfg.ParallelDownloads, 1, 6));
            var tasks = todo.Select(async it =>
            {
                await gate.WaitAsync(ct);
                try { await Task.Run(() => One(it, meter, ct), ct); }
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
                    Overall = meter.Fraction * 100;
                    ProgressText = meter.Text();
                    await Task.Delay(500);
                }
            });
            try { await Task.WhenAll(tasks); }
            catch (OperationCanceledException) { }
            Overall = meter.Fraction * 100;
            ProgressText = ct.IsCancellationRequested ? "Paused: it resumes where it stopped." : "";
        }
        finally
        {
            foreach (var it in todo.Where(i => i.State is PackState.Queued or PackState.Downloading or PackState.Verifying))
            {
                it.State = PartLength(it) > 0 ? PackState.Update : PackState.Missing;
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

    async Task One(PackItem it, Meter meter, CancellationToken ct)
    {
        string? sha = it.Asset.Sha256;
        if (it.State == PackState.Unchecked)
        {
            string dest = Dest(it)!;
            it.State = PackState.Verifying;
            string h = await Hash(dest, it, ct);
            if (h == sha)
            {
                lock (st) st.Checked[it.Name] = Key(sha!, new FileInfo(dest));
                it.State = PackState.Installed;
                return;
            }
            Log.Write($"{it.Name}: the zip in place has another sha256: downloaded again");
            meter.Add(0);
        }
        string part = PartPath(it)!, ready = ReadyPath(it)!;
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
            Log.Write($"{it.Name}: downloaded and checked");
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
        var ready = Items.Where(i => i.State == PackState.Ready).ToList();
        if (ready.Count == 0 && OldZips.Count == 0) return 0;
        string? why = ApplyBlocker();
        if (why != null)
        {
            if (ready.Count > 0) Log.Write($"{ready.Count} zip ready, installed when {why} no longer");
            UpdateSummary();
            return 0;
        }
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
        await Task.Run(Classify);
        UpdateSummary();
        if (n > 0) { Log.Write($"{n} zip installati"); Applied?.Invoke(); }
        return n;
    }

    void Install(PackItem it)
    {
        string ready = ReadyPath(it)!;
        string? sha = it.Asset.Sha256;
        switch (it.Kind)
        {
            case PackKind.Server:
                Directory.CreateDirectory(ServerDir);
                ZipFile.ExtractToDirectory(ready, ServerDir, true);
                File.Delete(ready);
                st.Server = $"{it.Name}|{sha}";
                break;
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
                string dest = Path.Combine(DataFolder!, it.Name);
                foreach (var old in LocalZones().Where(l => ZoneOf(l.Name).Equals(it.Zone, StringComparison.OrdinalIgnoreCase)
                                                             && !l.Name.Equals(it.Name, StringComparison.OrdinalIgnoreCase)))
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

    /// <summary>An old zip: deleted, or moved to data\old (setting "Delete old packs").</summary>
    void Retire(string path)
    {
        try
        {
            if (!File.Exists(path)) return;
            if (cfg.DeleteOld || DataFolder is null)
            {
                File.Delete(path);
                Log.Write("deleted " + path);
            }
            else
            {
                string dir = Path.Combine(DataFolder, "old");
                Directory.CreateDirectory(dir);
                File.Move(path, Path.Combine(dir, Path.GetFileName(path)), true);
                Log.Write($"moved {path} to {dir}");
            }
            st.Checked.Remove(Path.GetFileName(path));
        }
        catch (Exception e) { Log.Write($"could not remove {path}: {e.Message}"); }
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
            File.Copy(db, Path.Combine(DownloadDir!, "db.json.bak"), true);
            Files.WriteAtomic(db, root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
            Log.Write($"{changed} Ticino mods turned back on in mods\\db.json");
        }
        catch (Exception e) { Log.Write("mods\\db.json not read: " + e.Message); }
    }

    // ------------------------------------------------------------------------------------------- moving packs
    /// <summary>Moves the zone zips from mods into the data folder (`ticino_server adopt`): on one drive a rename.</summary>
    public async Task MoveZonesFromMods(IProgress<string> report)
    {
        if (DataFolder is null) throw new InvalidOperationException("Choose the packs folder first.");
        if (BeamNG.Running()) throw new InvalidOperationException("Close BeamNG: it keeps the zips in mods open.");
        var list = ZonesInMods.ToList();
        Directory.CreateDirectory(DataFolder);
        long total = list.Sum(f => f.Length), done = 0;
        foreach (var f in list)
        {
            report.Report($"{f.Name} ({Files.Size(done)} of {Files.Size(total)})");
            await Files.MoveAsync(f.FullName, Path.Combine(DataFolder, f.Name), new Progress<long>(n => done += n), CancellationToken.None);
            Log.Write($"moved {f.Name} from mods to {DataFolder}");
        }
        await Task.Run(Classify);
        UpdateSummary();
    }

    /// <summary>A new data folder: the zips (and the unfinished downloads) of the old one go with it.</summary>
    public async Task ChangeDataFolder(string? from, string to, bool move, IProgress<string> report)
    {
        if (move && from != null && Directory.Exists(from) && !Path.GetFullPath(from).Equals(Path.GetFullPath(to), StringComparison.OrdinalIgnoreCase))
        {
            if (ServerRunning()) throw new InvalidOperationException("Stop the server before moving the packs.");
            var files = new DirectoryInfo(from).EnumerateFiles("ticino_*.zip").ToList();
            string dl = Path.Combine(from, ".download");
            if (Directory.Exists(dl)) files.AddRange(new DirectoryInfo(dl).EnumerateFiles());
            long total = files.Sum(f => f.Length), done = 0;
            foreach (var f in files)
            {
                string rel = Path.GetRelativePath(from, f.FullName);
                report.Report($"{f.Name} ({Files.Size(done)} of {Files.Size(total)})");
                await Files.MoveAsync(f.FullName, Path.Combine(to, rel), new Progress<long>(n => done += n), CancellationToken.None);
            }
            Log.Write($"{files.Count} files moved from {from} to {to}");
        }
        cfg.DataFolder = to;
        cfg.Save();
        Directory.CreateDirectory(to);
        Raise(nameof(DataFolder));
        await Task.Run(Classify);
        UpdateSummary();
    }

    /// <summary>A sensible default for the data folder: the fixed drive with the most free space.</summary>
    public static string SuggestDataFolder()
    {
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
