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
            ServerStatus.Running => S.GameConnected ? "In gioco" : "Server in esecuzione",
            ServerStatus.Starting => "Avvio del server…",
            ServerStatus.Stopping => "Arresto del server…",
            _ => "Server fermo",
        };
        HeroLine.Text = S.Status switch
        {
            ServerStatus.Running when S.GameConnected => $"Il server prepara le zone intorno all'auto · {S.Car}",
            ServerStatus.Running => game ? "BeamNG è aperto: carica la mappa Ticino (Freeroam) per collegarlo." : "Pronto: premi Gioca.",
            ServerStatus.Starting => "Indicizza i pacchetti zona…",
            _ => P.InstalledZones > 0 ? "Premi Gioca: avvia il server e BeamNG direttamente nella mappa." : "Scarica prima la mappa.",
        };
        string dot = S.Status switch
        {
            ServerStatus.Running => S.GameConnected ? "SystemFillColorSuccessBrush" : "AccentFillColorDefaultBrush",
            ServerStatus.Starting or ServerStatus.Stopping => "SystemFillColorCautionBrush",
            _ => "SubtleFillColorSecondaryBrush",
        };
        HeroDot.Fill = TryFindResource(dot) as Brush ?? Brushes.Gray;
        HeroGlyph.Foreground = S.IsRunning ? Brushes.White : (TryFindResource("TextFillColorPrimaryBrush") as Brush ?? Brushes.Black);
        ServerLabel.Text = S.IsRunning ? "Ferma server" : "Avvia server";
        ServerGlyph.Text = S.IsRunning ? "" : "";
        ServerButton.IsEnabled = S.Status is ServerStatus.Running or ServerStatus.Stopped;
        PlayButton.IsEnabled = !game && BeamNG.FindGame(C) != null;
        PlayButton.ToolTip = game ? "BeamNG è già aperto" : BeamNG.FindGame(C) is null ? "BeamNG non trovato: sceglilo qui sotto" : null;

        // numbers
        ZonesValue.Text = P.Release is null ? (P.DataFolder is null ? "–" : $"{LocalZoneCount()}") : $"{P.InstalledZones} / {P.ReleaseZones}";
        TilesValue.Text = S.IsRunning ? $"{S.Units}" : "–";
        CacheValue.Text = S.IsRunning ? Files.Size(S.CacheMB * 1048576.0) : "–";
        ShapesValue.Text = S.IsRunning ? $"{S.Converted}" : "–";

        // bars
        UpdateBar.Visibility = P.NeedCount > 0 && !P.Busy && P.DataFolder != null && P.InstalledZones > 0 ? Visibility.Visible : Visibility.Collapsed;
        UpdateBar.Message = $"{P.NeedCount} pacchetti nuovi o cambiati ({Files.Size(P.NeedBytes)}).";
        string? setup = P.DataFolder is null ? "Scegli dove salvare la mappa e scaricala (circa 52 GB)."
            : P.Release != null && P.InstalledZones == 0 && P.NeedCount > 0 ? $"La mappa non è ancora scaricata: {Files.Size(P.NeedBytes)}."
            : P.Busy ? null
            : PackManager.ServerExe() is null && P.Release != null ? "Manca il programma del server: scaricalo nella pagina Download." : null;
        if (P.Busy) setup = null;
        SetupBar.Visibility = setup != null ? Visibility.Visible : Visibility.Collapsed;
        SetupBar.Message = setup ?? "";
        ModsBar.Visibility = P.ZonesInMods.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
        ModsBar.Message = $"{P.ZonesInMods.Count} zone ({Files.Size(P.ZonesInMods.Sum(f => f.Length))}) sono in mods: il gioco le monta tutte a ogni avvio (più di un minuto). Con il server stanno nella cartella dei pacchetti.";
        LuaBar.Visibility = baseLua == false && ServerPage.LuaOverrideInstalled() == false ? Visibility.Visible : Visibility.Collapsed;
        LuaBar.Message = "Questo pacchetto base carica le zone solo da mods. Finché non esce un base nuovo serve il Lua di prova del server (pagina Server).";
        ErrorBar.Visibility = P.Error != null ? Visibility.Visible : Visibility.Collapsed;
        ErrorBar.Message = P.Error ?? "";

        // this PC
        string? g = BeamNG.FindGame(C);
        GameCard.Description = g ?? "Non trovato nelle librerie di Steam: indicane la cartella.";
        UserCard.Description = BeamNG.UserFolder(C) + (Directory.Exists(BeamNG.Mods(C)) ? "" : " (non trovata: avvia BeamNG una volta)");
        DataCard.Description = P.DataFolder is null ? "Non ancora scelta (pagina Download)"
            : $"{P.DataFolder} · {Files.Size(Files.FreeSpace(P.DataFolder))} liberi";
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
            if (BeamNG.Running() && !Ui.Ask("BeamNG è aperto: senza server le zone intorno all'auto non arrivano più. Fermare il server?")) return;
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
        if (p is null) Ui.Info("BeamNG.drive non trovato: indicane la cartella in Home.");
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
        if (!Ui.Ask($"Spostare {P.ZonesInMods.Count} zone da\n{BeamNG.Mods(C)}\na\n{P.DataFolder}?")) return;
        try
        {
            IsEnabled = false;
            await P.MoveZonesFromMods(new Progress<string>(t => ModsBar.Message = "Spostamento: " + t));
        }
        catch (Exception ex) { Ui.Info(ex.Message); }
        finally { IsEnabled = true; Refresh(); }
    }

    void ChangeGame_Click(object sender, RoutedEventArgs e)
    {
        string? f = Ui.ChooseFolder("Cartella di BeamNG.drive (quella con Bin64)", BeamNG.FindGame(C));
        if (f is null) return;
        if (BeamNG.GameExe(f) is null) { Ui.Info("In questa cartella non c'è Bin64\\BeamNG.drive.x64.exe."); return; }
        C.GameFolder = f;
        C.Save();
        Refresh();
    }

    async void ChangeUser_Click(object sender, RoutedEventArgs e)
    {
        string? f = Ui.ChooseFolder("Cartella utente di BeamNG (quella con mods e settings)", BeamNG.UserFolder(C));
        if (f is null) return;
        if (!Directory.Exists(Path.Combine(f, "mods")) && !Ui.Ask("In questa cartella non c'è mods. Usarla comunque?")) return;
        C.UserFolder = f.Equals(BeamNG.DefaultUserFolder, StringComparison.OrdinalIgnoreCase) ? null : f;
        C.Save();
        await P.Refresh();
        Refresh();
    }

    void OpenUser_Click(object sender, RoutedEventArgs e) => Ui.Open(BeamNG.UserFolder(C));
    void OpenData_Click(object sender, RoutedEventArgs e) => Ui.Open(P.DataFolder);
}
