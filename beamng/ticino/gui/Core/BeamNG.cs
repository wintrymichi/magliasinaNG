using System.Diagnostics;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace TicinoServer.Core;

/// <summary>Where BeamNG and its user folder are, and whether the game runs.</summary>
public static class BeamNG
{
    public const string Level = "ticino";
    public const string ProcessName = "BeamNG.drive.x64";

    public static string DefaultUserFolder =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "BeamNG", "BeamNG.drive", "current");

    public static string UserFolder(AppConfig c) =>
        string.IsNullOrWhiteSpace(c.UserFolder) ? DefaultUserFolder : c.UserFolder!;

    public static string Mods(AppConfig c) => Path.Combine(UserFolder(c), "mods");
    public static string SettingsFile(AppConfig c) => Path.Combine(UserFolder(c), "settings", "ticino.json");
    public static string HelperDir(AppConfig c) => Path.Combine(UserFolder(c), "temp", "ticino", "helper");
    public static string ServeDir(AppConfig c) => Path.Combine(UserFolder(c), "temp", "ticino", "srv");
    public static string LevelCache(AppConfig c) => Path.Combine(UserFolder(c), "temp", "levels", Level);

    public static bool Running() => Process.GetProcessesByName(ProcessName).Length > 0;

    public static string? GameExe(string folder) =>
        File.Exists(Path.Combine(folder, "Bin64", "BeamNG.drive.x64.exe"))
            ? Path.Combine(folder, "Bin64", "BeamNG.drive.x64.exe") : null;

    /// <summary>The game folder: the one set in the app, else the Steam libraries (as install_ticino.ps1).</summary>
    static (DateTime at, string? key, string? game) found;

    public static string? FindGame(AppConfig c)
    {
        // read every second by the UI: the registry and libraryfolders.vdf once every 10 s
        if (found.key == c.GameFolder && DateTime.UtcNow - found.at < TimeSpan.FromSeconds(10)) return found.game;
        string? g = Search(c);
        found = (DateTime.UtcNow, c.GameFolder, g);
        return g;
    }

    static string? Search(AppConfig c)
    {
        if (!string.IsNullOrWhiteSpace(c.GameFolder) && GameExe(c.GameFolder!) != null) return c.GameFolder;
        var libs = new List<string>();
        try
        {
            using var k = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
            if (k?.GetValue("SteamPath") is string steam)
            {
                libs.Add(steam);
                string vdf = Path.Combine(steam, "steamapps", "libraryfolders.vdf");
                if (File.Exists(vdf))
                    foreach (Match m in Regex.Matches(File.ReadAllText(vdf), "\"path\"\\s+\"([^\"]+)\""))
                        libs.Add(m.Groups[1].Value.Replace(@"\\", @"\"));
            }
        }
        catch { /* no Steam */ }
        foreach (var lib in libs)
        {
            string g = Path.Combine(lib, "steamapps", "common", "BeamNG.drive");
            if (GameExe(g) != null) return g;
        }
        return null;
    }

    public const string HelperProcess = "ticino_helper";

    /// <summary>Packs mode, as start_ticino.ps1: the streaming helper of the installer's tools beside the game, when it
    /// is installed and settings\ticino.json does not turn it off. It ends with the game (--game-pid). Steam may start
    /// the game again in a process of its own: the helper follows the BeamNG process that runs after a few seconds.</summary>
    public static async Task StartHelper(AppConfig c)
    {
        string exe = Path.Combine(Installer.ToolsDir(c), HelperProcess + ".exe");
        if (!File.Exists(exe)) { Log.Write("no helper installed: the map works without it"); return; }
        if (!GameSettings.Load(SettingsFile(c)).Helper) return;
        if (Process.GetProcessesByName(HelperProcess).Length > 0) return;
        Process? live = null;
        for (int i = 0; i < 30 && live is null; i++)
        {
            await Task.Delay(3000);
            live = Process.GetProcessesByName(ProcessName).FirstOrDefault();
        }
        if (live is null) { Log.Write("BeamNG is not running after 90 s: no helper started"); return; }
        try
        {
            var psi = new ProcessStartInfo(exe)
            {
                WorkingDirectory = Installer.ToolsDir(c),
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            foreach (var a in new[] { "--user", UserFolder(c), "--game-pid", live.Id.ToString() }) psi.ArgumentList.Add(a);
            Process.Start(psi);
            Log.Write($"helper started beside the game (pid {live.Id})");
        }
        catch (Exception e) { Log.Write("helper not started: " + e.Message); }
    }

    /// <summary>Starts the game straight into the Ticino map (as start_ticino.ps1).</summary>
    public static Process? Start(AppConfig c)
    {
        string? game = FindGame(c);
        string? exe = game is null ? null : GameExe(game);
        if (exe is null) return null;
        var psi = new ProcessStartInfo(exe) { WorkingDirectory = game!, UseShellExecute = false };
        psi.ArgumentList.Add("-level");
        psi.ArgumentList.Add(Level + "/main.level.json");
        return Process.Start(psi);
    }
}
