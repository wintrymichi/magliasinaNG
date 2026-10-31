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
        // the hero
        HeroTitle.Text = S.Status switch
        {
            ServerStatus.Running => S.GameConnected ? "In game" : "Server running",
            ServerStatus.Starting => "Starting the server…",
            ServerStatus.Stopping => "Stopping the server…",
            _ => "Server stopped",
        };
        HeroLine.Text = S.Status switch
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
        PlayButton.IsEnabled = !game && BeamNG.FindGame(C) != null;
        PlayButton.ToolTip = game ? "BeamNG is already open" : BeamNG.FindGame(C) is null ? "BeamNG not found: choose its folder below" : null;

        // numbers
        ZonesValue.Text = P.Release is null ? (P.DataFolder is null ? "–" : $"{LocalZoneCount()}") : $"{P.InstalledZones} / {P.ReleaseZones}";
        TilesValue.Text = S.IsRunning ? $"{S.Units}" : "–";
        CacheValue.Text = S.IsRunning ? Files.Size(S.CacheMB * 1048576.0) : "–";
        ShapesValue.Text = S.IsRunning ? $"{S.Converted}" : "–";

        // bars
        UpdateBar.Visibility = P.NeedCount > 0 && !P.Busy && P.DataFolder != null && P.InstalledZones > 0 ? Visibility.Visible : Visibility.Collapsed;
        UpdateBar.Message = $"{P.NeedCount} new or changed packs ({Files.Size(P.NeedBytes)}).";
        string? setup = P.DataFolder is null ? "Choose where to keep the map and download it (about 52 GB)."
            : P.Release != null && P.InstalledZones == 0 && P.NeedCount > 0 ? $"The map is not downloaded yet: {Files.Size(P.NeedBytes)}."
            : P.Busy ? null
            : PackManager.ServerExe() is null && P.Release != null ? "The server program is missing: download it on the Downloads page." : null;
        if (P.Busy) setup = null;
        SetupBar.Visibility = setup != null ? Visibility.Visible : Visibility.Collapsed;
        SetupBar.Message = setup ?? "";
        ModsBar.Visibility = P.ZonesInMods.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
        ModsBar.Message = $"{P.ZonesInMods.Count} zones ({Files.Size(P.ZonesInMods.Sum(f => f.Length))}) are in mods: the game mounts all of them at every start (more than a minute). With the server they belong in the packs folder.";
        LuaBar.Visibility = baseLua == false && ServerPage.LuaOverrideInstalled() == false ? Visibility.Visible : Visibility.Collapsed;
        LuaBar.Message = "This base pack loads zones from mods only. Until a new base pack is out, the server's test Lua is needed (Server page).";
        ErrorBar.Visibility = P.Error != null ? Visibility.Visible : Visibility.Collapsed;
        ErrorBar.Message = P.Error ?? "";

        // this PC
        string? g = BeamNG.FindGame(C);
        GameCard.Description = g ?? "Not found in the Steam libraries: choose its folder.";
        UserCard.Description = BeamNG.UserFolder(C) + (Directory.Exists(BeamNG.Mods(C)) ? "" : " (not found: start BeamNG once)");
        DataCard.Description = P.DataFolder is null ? "Not chosen yet (Downloads page)"
            : $"{P.DataFolder} · {Files.Size(Files.FreeSpace(P.DataFolder))} free";
    }

    static int LocalZoneCount()
    {
        try
        {
            return Directory.Exists(App.Packs.DataFolder)
                ? Directory.EnumerateFiles(App.Packs.DataFolder!, "ticino_*.zip").Count() : 0;
        }
        catch { return 0; }
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
    void GoServer_Click(object sender, RoutedEventArgs e) => Ui.Main.Navigate("server");

    async void MoveFromMods_Click(object sender, RoutedEventArgs e)
    {
        if (P.DataFolder is null) { Ui.Main.Navigate("download"); return; }
        if (!Ui.Ask($"Move {P.ZonesInMods.Count} zones from\n{BeamNG.Mods(C)}\nto\n{P.DataFolder}?")) return;
        try
        {
            IsEnabled = false;
            await P.MoveZonesFromMods(new Progress<string>(t => ModsBar.Message = "Moving: " + t));
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
    void OpenData_Click(object sender, RoutedEventArgs e) => Ui.Open(P.DataFolder);
}
