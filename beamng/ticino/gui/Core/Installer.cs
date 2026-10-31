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

    public sealed record Info(string? Tag, string? Game, string? User, string? Mode, string? Data);

    public static Info? Read(AppConfig c)
    {
        try
        {
            if (!Present(c)) return null;
            if (JsonNode.Parse(File.ReadAllText(InstallJson(c))) is not JsonObject o) return null;
            return new Info(Str(o, "tag"), Str(o, "game"), Str(o, "user"), Str(o, "mode"), Str(o, "data"));
        }
        catch (Exception e)
        {
            Log.Write("install.json not readable: " + e.Message);
            return null;
        }
    }

    static string? Str(JsonObject o, string k) =>
        o[k] is JsonValue v && v.TryGetValue(out string? s) && !string.IsNullOrWhiteSpace(s) ? s : null;

    /// <summary>The installer's packs folder: install.json "data" in server mode, else "data" of ticino_server.json,
    /// else &lt;user&gt;\ticino_data if it is there.</summary>
    public static string? DataFolder(AppConfig c)
    {
        var i = Read(c);
        if (i?.Mode == "server" && i.Data != null) return i.Data;
        try
        {
            if (File.Exists(ServerJson(c)) && JsonNode.Parse(File.ReadAllText(ServerJson(c))) is JsonObject s &&
                Str(s, "data") is { } d)
                return d;
        }
        catch { /* not valid JSON: the server ignores it too */ }
        string def = Path.Combine(BeamNG.UserFolder(c), "ticino_data");
        return Directory.Exists(def) ? def : null;
    }

    /// <summary>First start of the app on a PC the installer has set up: take over its packs folder (server mode
    /// only: in packs mode the zones are in mods), release and game folder, so the app and "Start Ticino" use one
    /// set of zips. Returns true when the settings changed.</summary>
    public static bool Adopt(AppConfig c, bool newSettings)
    {
        var i = Read(c);
        if (i is null) return false;
        bool changed = false;
        if (c.DataFolder is null && i.Mode == "server" && DataFolder(c) is { } d && Directory.Exists(d))
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
    }

    static void Merge(string path, Action<JsonObject> set)
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
            if (o.ToJsonString() == before && File.Exists(path)) return;
            Files.WriteAtomic(path, after);
        }
        catch (Exception e) { Log.Write($"{Path.GetFileName(path)} not written: {e.Message}"); }
    }
}
