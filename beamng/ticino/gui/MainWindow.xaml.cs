using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using TicinoServer.Core;
using TicinoServer.Pages;

namespace TicinoServer;

public partial class MainWindow : Window
{
    readonly Dictionary<string, UserControl> pages = new();
    readonly DispatcherTimer tick = new() { Interval = TimeSpan.FromSeconds(1) };
    readonly DispatcherTimer autoCheck = new() { Interval = TimeSpan.FromHours(6) };
    bool gameWasRunning;

    public MainWindow()
    {
        InitializeComponent();
        Nav.SelectedIndex = 0;
        tick.Tick += (_, _) => Tick();
        tick.Start();
        autoCheck.Tick += async (_, _) => await CheckForUpdates(false);
        autoCheck.Start();
        Loaded += async (_, _) => await OnFirstLoad();
        App.Server.PropertyChanged += (_, _) => Dispatcher.BeginInvoke(UpdateStatus);
        App.Packs.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(PackManager.NeedCount) or nameof(PackManager.ReadyCount))
                Dispatcher.BeginInvoke(UpdateBadge);
        };
    }

    public void Navigate(string tag)
    {
        foreach (ListBoxItem i in Nav.Items)
            if ((string)i.Tag == tag) { Nav.SelectedItem = i; return; }
    }

    UserControl PageFor(string tag)
    {
        if (!pages.TryGetValue(tag, out var p))
        {
            p = tag switch
            {
                "graphics" => new GraphicsPage(),
                "download" => new DownloadPage(),
                "server" => new ServerPage(),
                "about" => new AboutPage(),
                _ => new HomePage(),
            };
            pages[tag] = p;
        }
        return p;
    }

    void Nav_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (Nav.SelectedItem is ListBoxItem i) Page.Content = PageFor((string)i.Tag);
    }

    async Task OnFirstLoad()
    {
        if (App.Config.StartServerWithApp && App.Packs.DataFolder != null)
        {
            await App.Packs.ApplyPending();
            App.Server.Start();
        }
        if (App.Config.CheckOnStart) await CheckForUpdates(true);
    }

    /// <summary>Reads the release; with "download automatically" on, downloads what changed.</summary>
    public async Task CheckForUpdates(bool startup)
    {
        await App.Packs.Refresh();
        if (App.Config.AutoDownload && App.Packs.DataFolder != null && App.Packs.NeedCount > 0 && App.Packs.Error is null)
        {
            Log.Write($"automatic update: {App.Packs.NeedCount} zip");
            await App.Packs.DownloadAll();
        }
        else if (App.Packs.ReadyCount > 0) await App.Packs.ApplyPending();
    }

    void Tick()
    {
        App.Server.Poll();
        bool game = BeamNG.Running();
        if (gameWasRunning && !game)
        {
            Log.Write("BeamNG closed");
            if (App.Config.StopServerWithGame && App.Server.IsRunning) _ = StopServerThenApply();
            else _ = App.Packs.ApplyPending();
        }
        gameWasRunning = game;
        UpdateStatus();
        if (Page.Content is ITickable t) t.Tick();
    }

    async Task StopServerThenApply()
    {
        await App.Server.Stop();
        await App.Packs.ApplyPending();
    }

    void UpdateStatus()
    {
        var s = App.Server;
        StatusTitle.Text = s.Status switch
        {
            ServerStatus.Running => "Server in esecuzione",
            ServerStatus.Starting => "Server in avvio…",
            ServerStatus.Stopping => "Server in arresto…",
            _ => "Server fermo",
        };
        string key = s.Status switch
        {
            ServerStatus.Running => s.GameConnected ? "SystemFillColorSuccessBrush" : "AccentFillColorDefaultBrush",
            ServerStatus.Starting or ServerStatus.Stopping => "SystemFillColorCautionBrush",
            _ => "TextFillColorTertiaryBrush",
        };
        StatusDot.Fill = TryFindResource(key) as Brush ?? Brushes.Gray;
        StatusLine.Text = s.GameConnected ? "BeamNG collegato" : BeamNG.Running() ? "BeamNG aperto" : "BeamNG chiuso";
    }

    void UpdateBadge()
    {
        int n = App.Packs.NeedCount + App.Packs.ReadyCount;
        NavBadge.Visibility = n > 0 ? Visibility.Visible : Visibility.Collapsed;
        NavBadgeText.Text = n.ToString();
    }

    protected override void OnClosing(CancelEventArgs e)
    {
        if (App.Server.IsRunning && BeamNG.Running())
        {
            var r = MessageBox.Show(this,
                "BeamNG sta usando il server: chiudendo Ticino Server la mappa smette di caricare le zone intorno all'auto.\n\nChiudere comunque?",
                "Ticino Server", MessageBoxButton.YesNo, MessageBoxImage.Warning);
            if (r != MessageBoxResult.Yes) { e.Cancel = true; return; }
        }
        if (App.Packs.Busy) App.Packs.Pause();
        base.OnClosing(e);
    }
}

/// <summary>A page that refreshes its numbers once a second while it is shown.</summary>
public interface ITickable
{
    void Tick();
}
