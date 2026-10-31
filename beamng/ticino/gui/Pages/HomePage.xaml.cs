using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using TicinoServer.Core;

namespace TicinoServer.Pages;

public partial class HomePage : UserControl, ITickable
{
    static PackManager P => App.Packs;
    static ServerHost S => App.Server;
    static AppConfig C => App.Config;
    int slow;
    bool? baseLua;

    public HomePage()
    {
        InitializeComponent();
        P.PropertyChanged += (_, _) => Dispatcher.BeginInvoke(Refresh);
        P.Applied += () => Dispatcher.BeginInvoke(() => { baseLua = P.BaseHasServerLua(); Refresh(); });
        S.PropertyChanged += (_, _) => Dispatcher.BeginInvoke(Refresh);
        baseLua = P.BaseHasServerLua();
        Refresh();
    }

    public void Tick()
    {
        if (++slow % 10 == 0) baseLua = P.BaseHasServerLua();
        Refresh();
    }

    void Refresh()
    {
        bool game = BeamNG.Running();
        bool packs = P.PacksMode && !S.IsRunning;
        // the hero
        HeroTitle.Text = packs ? (game ? "In game" : "Ready to play") : S.Status switch
        {
            ServerStatus.Running => S.GameConnected ? "In game" : "Server running",
            ServerStatus.Starting => "Starting the server…",
            ServerStatus.Stopping => "Stopping the server…",
            _ => "Server stopped",
        };
        HeroLine.Text = packs
            ? game ? "Packs mode: BeamNG loads the zones from its mods folder." :
              P.Release != null && P.InstalledZones == 0 ? "Download the map first." :
              "Packs mode: the zones are in BeamNG's mods folder. Press Play: BeamNG starts straight into the map."
            : S.Status switch
        {
            ServerStatus.Running when S.GameConnected => $"The server is preparing the zones around the car · {S.Car}",
            ServerStatus.Running => game ? "BeamNG is open: load the Ticino map (Freeroam) to connect it." : "Ready: press Play.",
            ServerStatus.Starting => "Indexing the zone packs…",
            _ => P.InstalledZones > 0 ? "Press Play: starts the server and BeamNG straight into the map." : "Download the map first.",
        };
        string dot = S.Status switch
        {
            ServerStatus.Running => S.GameConnected ? "SystemFillColorSuccessBrush" : "AccentFillColorDefaultBrush",
            ServerStatus.Starting or ServerStatus.Stopping => "SystemFillColorCautionBrush",
            _ => "SubtleFillColorSecondaryBrush",
        };
        HeroDot.Fill = TryFindResource(dot) as Brush ?? Brushes.Gray;
        HeroGlyph.Foreground = S.IsRunning ? Brushes.White : (TryFindResource("TextFillColorPrimaryBrush") as Brush ?? Brushes.Black);
        ServerLabel.Text = S.IsRunning ? "Stop server" : "Start server";
        ServerGlyph.Text = S.IsRunning ? "" : "";
        ServerButton.IsEnabled = S.Status is ServerStatus.Running or ServerStatus.Stopped;
        // packs mode has no server to start: the zones are mounted by the game
        ServerButton.Visibility = packs ? Visibility.Collapsed : Visibility.Visible;
        PlayButton.IsEnabled = !game && BeamNG.FindGame(C) != null;
        PlayButton.ToolTip = game ? "BeamNG is already open" : BeamNG.FindGame(C) is null ? "BeamNG not found: choose its folder below" : null;

        // numbers
        ZonesValue.Text = P.Release is null ? (P.ZoneHome is null ? "–" : $"{P.LocalZoneCount()}") : $"{P.InstalledZones} / {P.ReleaseZones}";
        TilesValue.Text = S.IsRunning ? $"{S.Units}" : "–";
        CacheValue.Text = S.IsRunning ? Files.Size(S.CacheMB * 1048576.0) : "–";
        ShapesValue.Text = S.IsRunning ? $"{S.Converted}" : "–";

        // bars
        UpdateBar.Visibility = P.NeedCount > 0 && !P.Busy && P.ZoneHome != null && P.InstalledZones > 0 ? Visibility.Visible : Visibility.Collapsed;
        UpdateBar.Message = P.NeedBytes > 0 ? $"{P.NeedCount} new or changed packs ({Files.Size(P.NeedBytes)})."
            : $"{P.NeedCount} packs in place to check against the release (sha256, no download).";
        string? setup = P.ZoneHome is null ? "Choose where to keep the map and download it (about 52 GB)."
            : P.Release != null && P.InstalledZones == 0 && P.NeedCount > 0 ? $"The map is not downloaded yet: {Files.Size(P.NeedBytes)}."
            : P.Busy || P.PacksMode ? null
            : PackManager.ServerExe(C) is null && P.Release != null ? "The server program is missing: download it on the Downloads page." : null;
        if (P.Busy) setup = null;
        SetupBar.Visibility = setup != null ? Visibility.Visible : Visibility.Collapsed;
        SetupBar.Message = setup ?? "";
        ModsBar.Visibility = P.ZonesInMods.Count > 0 && !(P.PacksMode && baseLua == false) ? Visibility.Visible : Visibility.Collapsed;
        ModsBar.Title = P.PacksMode ? "Start the game faster" : "Zones in the mods folder";
        ModsBar.Severity = P.PacksMode ? "Info" : "Warning";
        ModsBar.Message = P.PacksMode
            ? $"The game mounts all {P.ZonesInMods.Count} zones in mods ({Files.Size(P.ZonesInMods.Sum(f => f.Length))}) at every start (more than a minute). Move them to a packs folder and the server loads only the zones around the car."
            : $"{P.ZonesInMods.Count} zones ({Files.Size(P.ZonesInMods.Sum(f => f.Length))}) are in mods: the game mounts all of them at every start (more than a minute). With the server they belong in the packs folder.";
        // an old base loads zones from mods only: what packs mode does anyway
        LuaBar.Visibility = baseLua == false && !P.PacksMode || ServerPage.LuaOverrideInstalled() ? Visibility.Visible : Visibility.Collapsed;
        LuaBar.Message = ServerPage.LuaOverrideInstalled()
            ? "A test copy of the server's Lua in the BeamNG user folder hides the base pack's Lua: remove it on the Server page."
            : "This base pack loads zones from mods only: update it on the Downloads page.";
        ErrorBar.Visibility = P.Error != null ? Visibility.Visible : Visibility.Collapsed;
        ErrorBar.Message = P.Error ?? "";

        // this PC
        string? g = BeamNG.FindGame(C);
        GameCard.Description = g ?? "Not found in the Steam libraries: choose its folder.";
        UserCard.Description = BeamNG.UserFolder(C) + (Directory.Exists(BeamNG.Mods(C)) ? "" : " (not found: start BeamNG once)");
        DataCard.Description = P.PacksMode ? $"In BeamNG's mods folder (packs mode) · {Files.Size(Files.FreeSpace(BeamNG.Mods(C)))} free"
            : P.DataFolder is null ? "Not chosen yet (Downloads page)"
            : $"{P.DataFolder} · {Files.Size(Files.FreeSpace(P.DataFolder))} free";
    }

    async void Server_Click(object sender, RoutedEventArgs e)
    {
        if (S.IsRunning)
        {
            if (BeamNG.Running() && !Ui.Ask("BeamNG is open: without the server the zones around the car stop coming. Stop the server?")) return;
            await S.Stop();
            await P.ApplyPending();
            return;
        }
        await StartServer();
    }

    static async Task<bool> StartServer()
    {
        await P.ApplyPending();
        string? err = S.Start();
        if (err != null) { Ui.Info(err); return false; }
        return true;
    }

    async void Play_Click(object sender, RoutedEventArgs e)
    {
        if (P.PacksMode && !S.IsRunning)
        {
            // as "Start Ticino" in packs mode: the game mounts the zones in mods, the helper (if installed) beside it
            await P.ApplyPending();
            if (BeamNG.Start(C) is null) { Ui.Info("BeamNG.drive not found: choose its folder on the Home page."); return; }
            Log.Write("BeamNG started into the Ticino map (packs mode)");
            await BeamNG.StartHelper(C);
            return;
        }
        if (C.StartServerWithGame && !S.IsRunning && !await StartServer()) return;
        var p = BeamNG.Start(C);
        if (p is null) Ui.Info("BeamNG.drive not found: choose its folder on the Home page.");
        else Log.Write("BeamNG started into the Ticino map");
    }

    async void Update_Click(object sender, RoutedEventArgs e)
    {
        Ui.Main.Navigate("download");
        await P.DownloadAll();
    }

    void GoDownload_Click(object sender, RoutedEventArgs e) => Ui.Main.Navigate("download");
    void Lua_Click(object sender, RoutedEventArgs e) => Ui.Main.Navigate(ServerPage.LuaOverrideInstalled() ? "server" : "download");

    async void MoveFromMods_Click(object sender, RoutedEventArgs e)
    {
        if (BeamNG.Running()) { Ui.Info("Close BeamNG first: it keeps the zips in mods open."); return; }
        string? to = P.DataFolder;
        if (to is null)
        {
            to = Ui.ChooseFolder("Folder for the Ticino zone packs (on the disk of mods moving is instant)", P.SuggestDataFolder());
            if (to is null) return;
        }
        string size = Files.Size(P.ZonesInMods.Sum(f => f.Length));
        if (!Ui.Ask($"Move {P.ZonesInMods.Count} zones ({size}) from\n{BeamNG.Mods(C)}\nto\n{to}?\n\nFrom then on the server loads the zones around the car, and \"Start Ticino\" starts it too.")) return;
        try
        {
            IsEnabled = false;
            if (P.DataFolder is null) await P.ChangeDataFolder(null, to, false, new Progress<string>(_ => { }));
            await P.MoveZonesFromMods(new Progress<string>(t => ModsBar.Message = "Moving: " + t));
            // server mode now: the server program comes with the next check (packs mode does not download it)
            await P.Refresh();
            if (PackManager.ServerExe(C) is null) await P.DownloadAll(i => i.Kind == PackKind.Server);
        }
        catch (Exception ex) { Ui.Info(ex.Message); }
        finally { IsEnabled = true; Refresh(); }
    }

    void ChangeGame_Click(object sender, RoutedEventArgs e)
    {
        string? f = Ui.ChooseFolder("BeamNG.drive folder (the one with Bin64)", BeamNG.FindGame(C));
        if (f is null) return;
        if (BeamNG.GameExe(f) is null) { Ui.Info("This folder has no Bin64\\BeamNG.drive.x64.exe."); return; }
        C.GameFolder = f;
        C.Save();
        Refresh();
    }

    async void ChangeUser_Click(object sender, RoutedEventArgs e)
    {
        string? f = Ui.ChooseFolder("BeamNG user folder (the one with mods and settings)", BeamNG.UserFolder(C));
        if (f is null) return;
        if (!Directory.Exists(Path.Combine(f, "mods")) && !Ui.Ask("This folder has no mods folder. Use it anyway?")) return;
        C.UserFolder = f.Equals(BeamNG.DefaultUserFolder, StringComparison.OrdinalIgnoreCase) ? null : f;
        C.Save();
        await P.Refresh();
        Refresh();
    }

    void OpenUser_Click(object sender, RoutedEventArgs e) => Ui.Open(BeamNG.UserFolder(C));
    void OpenData_Click(object sender, RoutedEventArgs e) => Ui.Open(P.PacksMode ? BeamNG.Mods(C) : P.DataFolder);
}
