using System.Text.Json;
using System.Text.Json.Nodes;

namespace TicinoServer.Core;

/// <summary>What install_ticino.ps1 leaves in &lt;user&gt;\ticino_tools, so the app and the installer share one setup:
/// install.json = {tag, base, game, user, mode "server"|"packs", data, installed}, ticino_server.exe with its stamp
/// server.sha256, and ticino_server.json = the settings "Start Ticino" starts the server with (user, data, tag from
/// the installer; cacheGB, workers, dae from the app). The installer keeps keys it does not write.</summary>
public static class Installer
{
    public const string ServerExeName = "ticino_server.exe";

    public static string ToolsDir(AppConfig c) => Path.Combine(BeamNG.UserFolder(c), "ticino_tools");
    static string InstallJson(AppConfig c) => Path.Combine(ToolsDir(c), "install.json");
    public static string ServerJson(AppConfig c) => Path.Combine(ToolsDir(c), "ticino_server.json");
    public static string ServerStamp(AppConfig c) => Path.Combine(ToolsDir(c), "server.sha256");

    /// <summary>The installer has set up this user folder (install.json in ticino_tools).</summary>
    public static bool Present(AppConfig c) => File.Exists(InstallJson(c));

    public sealed record Info(string? Tag, string? Game, string? User, string? Mode, string? Data, string? Base);

    public static Info? Read(AppConfig c)
    {
        try
        {
            if (!Present(c)) return null;
            if (JsonNode.Parse(File.ReadAllText(InstallJson(c))) is not JsonObject o) return null;
            return new Info(Str(o, "tag"), Str(o, "game"), Str(o, "user"), Str(o, "mode"), Str(o, "data"), Str(o, "base"));
        }
        catch (Exception e)
        {
            Log.Write("install.json not readable: " + e.Message);
            return null;
        }
    }

    static string? Str(JsonObject o, string k) =>
        o[k] is JsonValue v && v.TryGetValue(out string? s) && !string.IsNullOrWhiteSpace(s) ? s : null;

    /// <summary>The installer's packs folder: install.json "data", else "data" of ticino_server.json, else
    /// &lt;user&gt;\ticino_data: the first of them that exists (in either mode: a PC moved from packs to server mode, or
    /// installed twice, has its zones there whatever install.json's mode says).</summary>
    public static string? DataFolder(AppConfig c)
    {
        var list = new List<string?> { Read(c)?.Data };
        try
        {
            if (File.Exists(ServerJson(c)) && JsonNode.Parse(File.ReadAllText(ServerJson(c))) is JsonObject s)
                list.Add(Str(s, "data"));
        }
        catch { /* not valid JSON: the server ignores it too */ }
        list.Add(Path.Combine(BeamNG.UserFolder(c), "ticino_data"));
        foreach (var d in list)
            if (d != null && Directory.Exists(d)) return d;
        return null;
    }

    static bool HasZones(string dir)
    {
        try
        {
            return Directory.EnumerateFiles(dir, "ticino_*.zip")
                .Any(f => !Path.GetFileName(f).StartsWith("ticino_base", StringComparison.OrdinalIgnoreCase));
        }
        catch { return false; }
    }

    /// <summary>Start of the app on a PC the installer has set up: take over its packs folder (when it is in server
    /// mode or holds zones: the PC test of 2026-10-31 had 89 zones in "D:\ticino zones", named in install.json, and the
    /// app showed 0 of 89 with "not chosen yet"), and on the first start its release and game folder, so the app and
    /// "Start Ticino" use one set of zips. Returns true when the settings changed.</summary>
    public static bool Adopt(AppConfig c, bool newSettings)
    {
        var i = Read(c);
        if (i is null) return false;
        bool changed = false;
        if (c.DataFolder is null && DataFolder(c) is { } d &&
            (i.Mode == "server" || HasZones(d)) &&
            !Path.GetFullPath(d).Equals(Path.GetFullPath(BeamNG.Mods(c)), StringComparison.OrdinalIgnoreCase))
        {
            c.DataFolder = d;
            changed = true;
            Log.Write($"packs folder of the installer taken over: {d}");
        }
        if (newSettings && i.Tag != null && i.Tag != c.Tag)
        {
            c.Tag = i.Tag;
            changed = true;
            Log.Write($"release of the installer taken over: {i.Tag}");
        }
        if (c.GameFolder is null && i.Game != null && BeamNG.GameExe(i.Game) != null)
        {
            c.GameFolder = i.Game;
            changed = true;
        }
        return changed;
    }

    /// <summary>Writes the app's server settings into ticino_server.json beside the installer's server (and the
    /// app's own copy), keeping every other key; and the packs folder into install.json, so the next run of the
    /// installer keeps the zips where the app has them.</summary>
    public static void Sync(AppConfig c, string? ownServerDir)
    {
        var files = new List<string>();
        if (Present(c)) files.Add(ServerJson(c));
        if (ownServerDir != null && File.Exists(Path.Combine(ownServerDir, ServerExeName)))
            files.Add(Path.Combine(ownServerDir, "ticino_server.json"));
        foreach (var f in files)
            Merge(f, o =>
            {
                o["user"] = BeamNG.UserFolder(c);
                if (c.DataFolder != null) o["data"] = c.DataFolder;
                o["tag"] = c.Tag;
                o["cacheGB"] = c.CacheGB;
                o["workers"] = c.Workers;
                o["dae"] = !c.Cdae;
            });
        if (Present(c) && c.DataFolder != null && Read(c)?.Data != c.DataFolder)
            Merge(InstallJson(c), o => o["data"] = c.DataFolder);
    }

    /// <summary>The zones moved out of mods (or back): "Start Ticino" starts the server only in mode "server".</summary>
    public static void SetMode(AppConfig c, string mode, string? data)
    {
        if (!Present(c) || Read(c)?.Mode == mode) return;
        Merge(InstallJson(c), o =>
        {
            o["mode"] = mode;
            if (data != null) o["data"] = data;
        });
        Log.Write($"install.json: mode {mode}");
        UpdateLauncher(c);
    }

    /// <summary>A new base pack went into mods: install.json "base" and the installer's ticino_download\installed.json
    /// name it as the installer does ("name|sha256"). The PC test of 1.1.1 found install.json still naming the base of
    /// the installer's run after the app had installed a newer one, and the installer clears the level cache whenever
    /// installed.json names another base. Also called when the base in mods is the release's and checked (the PC test
    /// of 1.1.2: an old value stayed until the app installed the next base).</summary>
    public static void SetBase(AppConfig c, string tag)
    {
        if (!Present(c)) return;
        bool changed = false;
        foreach (var f in new[] { InstallJson(c), Path.Combine(BeamNG.UserFolder(c), "ticino_download", "installed.json") })
            if (File.Exists(f)) changed |= Merge(f, o => o["base"] = tag);
        if (changed) Log.Write($"install.json: base {tag.Split('|')[0]}");
    }

    /// <summary>"Start Ticino" (the desktop shortcut runs ticino_tools\Start Ticino.bat, which runs start_ticino.ps1)
    /// of an installer older than the server mode starts the game and the helper only: with the zones out of mods the
    /// map then loads with no zone at all ("the zone packs are neither in mods nor served", PC test of 1.1.1, script of
    /// 12c25f3). The app carries the launcher of its commit (beamng/ticino/install) and puts it in place when the one
    /// there does not know the server; a newer one from the installer is left alone.</summary>
    public static void UpdateLauncher(AppConfig c)
    {
        if (!Present(c)) return;
        try
        {
            string dir = ToolsDir(c), ps1 = Path.Combine(dir, "start_ticino.ps1"), bat = Path.Combine(dir, "Start Ticino.bat");
            bool old = !File.Exists(ps1) || !File.ReadAllText(ps1).Contains(ServerExeName, StringComparison.OrdinalIgnoreCase);
            if (old) WriteResource("start_ticino.ps1", ps1);
            if (!File.Exists(bat)) WriteResource("Start Ticino.bat", bat);
            if (old) Log.Write($"Start Ticino updated: {ps1} now starts the server in server mode");
        }
        catch (Exception e) { Log.Write("Start Ticino not updated: " + e.Message); }
    }

    static void WriteResource(string name, string path)
    {
        using var s = typeof(Installer).Assembly.GetManifestResourceStream(name)
                      ?? throw new InvalidOperationException($"{name} is not in the app");
        using var m = new MemoryStream();
        s.CopyTo(m);
        Files.WriteAtomic(path, m.ToArray());
    }

    /// <summary>Sets keys of a JSON file, keeping the others. True when the file was written.</summary>
    static bool Merge(string path, Action<JsonObject> set)
    {
        try
        {
            JsonObject o = new();
            if (File.Exists(path))
                try { if (JsonNode.Parse(File.ReadAllText(path)) is JsonObject r) o = r; }
                catch { /* rewritten whole */ }
            string before = o.ToJsonString();
            set(o);
            string after = o.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
            if (o.ToJsonString() == before && File.Exists(path)) return false;
            Files.WriteAtomic(path, after);
            return true;
        }
        catch (Exception e)
        {
            Log.Write($"{Path.GetFileName(path)} not written: {e.Message}");
            return false;
        }
    }
}
