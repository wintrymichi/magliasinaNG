using System.Globalization;
using System.Windows;
using System.Windows.Threading;
using TicinoServer.Core;

namespace TicinoServer;

public partial class App : Application
{
    Mutex? single;

    /// <summary>Started with --screenshots: no startup check, no timers that change the pages.</summary>
    public static bool ShotMode { get; private set; }

    /// <summary>The app's state, shared by every page.</summary>
    public static AppConfig Config { get; private set; } = null!;
    public static PackManager Packs { get; private set; } = null!;
    public static ServerHost Server { get; private set; } = null!;
    public static AppUpdate Update { get; } = new();

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        CultureInfo.DefaultThreadCurrentCulture = Files.Culture;
        CultureInfo.DefaultThreadCurrentUICulture = Files.Culture;
        DispatcherUnhandledException += OnUnhandled;
        TaskScheduler.UnobservedTaskException += (_, a) => { Log.Write("task: " + a.Exception?.GetBaseException().Message); a.SetObserved(); };

        string? shots = null;
        for (int i = 0; i < e.Args.Length; i++)
            if (e.Args[i] == "--screenshots" && i + 1 < e.Args.Length) shots = e.Args[++i];
        // ticino_gui.yml: the version of app_ticino.zip on a release, read as the update check reads it
        int probe = Array.IndexOf(e.Args, "--probe-update");
        if (probe >= 0 && probe + 2 < e.Args.Length)
        {
            _ = ProbeUpdate(e.Args[probe + 1], e.Args[probe + 2]);
            return;
        }

        ShotMode = shots != null;
        if (shots is null)
        {
            single = new Mutex(true, @"Local\TicinoServer.App", out bool first);
            if (!first)
            {
                MessageBox.Show("Ticino Server is already open.", "Ticino Server", MessageBoxButton.OK, MessageBoxImage.Information);
                Shutdown();
                return;
            }
        }

        bool firstStart = !AppConfig.Exists;
        Config = AppConfig.Load();
        // also in screenshot mode: the workflow's test of a moved install needs it (no install.json on the runner otherwise)
        if (Installer.Adopt(Config, firstStart) || Config.Migrated) Config.Save();
        Installer.UpdateLauncher(Config);
        Packs = new PackManager(Config);
        Server = new ServerHost(Config);
        Packs.ServerRunning = () => Server.IsRunning;
        Server.PacksMode = () => Packs.PacksMode;
        if (!ShotMode) Packs.ScanMods();
        Log.Write($"Ticino Server {typeof(App).Assembly.GetName().Version} started");
        if (!ShotMode) AppUpdate.CleanUp(e.Args.Contains("--after-update"));

        var w = new MainWindow();
        MainWindow = w;
        if (shots != null)
        {
            _ = Screenshots.Run(w, shots);
            return;
        }
        w.Show();
    }

    async Task ProbeUpdate(string tag, string output)
    {
        string result;
        try
        {
            var rel = await new GitHub().GetRelease(AppConfig.Load().Repo, tag, CancellationToken.None);
            var a = rel.Assets.FirstOrDefault(x => x.Name == AppUpdate.AssetName)
                    ?? throw new InvalidOperationException($"no {AppUpdate.AssetName} on {tag}");
            result = await Task.Run(() => Update.RemoteVersion(a)) ?? "none";
        }
        catch (Exception x) { result = "error: " + x.Message; }
        File.WriteAllText(output, result);
        Shutdown();
    }

    void OnUnhandled(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        Log.Write("error: " + e.Exception);
        MessageBox.Show(e.Exception.Message, "Ticino Server: error", MessageBoxButton.OK, MessageBoxImage.Error);
        e.Handled = true;
    }

    protected override void OnExit(ExitEventArgs e)
    {
        try { Server?.StopNow(); } catch { }
        single?.Dispose();
        base.OnExit(e);
    }
}
