using System.Windows;
using System.Windows.Controls;
using TicinoServer.Core;

namespace TicinoServer.Pages;

public partial class ServerPage : UserControl, ITickable
{
    static AppConfig C => App.Config;
    bool loading = true;

    public ServerPage()
    {
        InitializeComponent();
        Workers.Maximum = Math.Max(2, Environment.ProcessorCount);
        Cache.Value = C.CacheGB;
        Workers.Value = C.Workers;
        Ahead.Value = C.Ahead;
        Cdae.IsChecked = C.Cdae;
        WithGame.IsChecked = C.StartServerWithGame;
        StopWithGame.IsChecked = C.StopServerWithGame;
        WithApp.IsChecked = C.StartServerWithApp;
        UpdateServer.IsChecked = C.UpdateServer;
        loading = false;
        Labels();
        LogBox.Text = App.Server.LogText;
        LogBox.ScrollToEnd();
        App.Server.Output += line => Dispatcher.BeginInvoke(() =>
        {
            bool atEnd = LogBox.VerticalOffset + LogBox.ViewportHeight >= LogBox.ExtentHeight - 4;
            LogBox.AppendText(line + Environment.NewLine);
            if (LogBox.Text.Length > 400_000) LogBox.Text = LogBox.Text[^300_000..];
            if (atEnd) LogBox.ScrollToEnd();
        });
        Tick();
    }

    static string LuaDir => Path.Combine(BeamNG.UserFolder(C), "lua", "ge", "extensions", "ticino");
    /// <summary>Is the server's test Lua in the user folder (it overrides the base pack's)? Only the server's first
    /// tests put it there: the base pack has had the server Lua since d945d41.</summary>
    public static bool LuaOverrideInstalled() => File.Exists(Path.Combine(LuaDir, "files.lua"));

    public void Tick()
    {
        bool? baseLua = App.Packs.BaseHasServerLua();
        bool have = LuaOverrideInstalled();
        LuaBar.Visibility = baseLua == false && !App.Packs.PacksMode || have ? Visibility.Visible : Visibility.Collapsed;
        LuaBar.Severity = "Warning";
        LuaBar.Title = have ? "Server test Lua" : "Old base pack";
        if (have)
        {
            LuaBar.Message = "A test copy of the server's Lua is in the BeamNG user folder (lua\\ge\\extensions\\ticino): it hides the base pack's Lua. Remove it.";
            LuaButton.Content = "Remove";
        }
        else
        {
            LuaBar.Message = "The installed base pack is older than the server and loads zones from mods only: update it on the Downloads page.";
            LuaButton.Content = "Downloads";
        }
        string? exe = PackManager.ServerExe(C);
        ExeCard.Description = App.Packs.PacksMode && !App.Server.IsRunning
            ? "Not used: the map is installed in packs mode (the zones in mods). Move them to a packs folder on the Home page to use the server."
            : exe is null ? "Not downloaded yet (Downloads page)."
            : App.Server.External ? $"{exe} · running, started by Start Ticino" : exe;
    }

    void Labels()
    {
        CacheText.Text = $"{Cache.Value:0} GB";
        WorkersText.Text = $"{Workers.Value:0}";
        AheadText.Text = $"{Ahead.Value:0}";
    }

    void Changed(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (loading) return;
        C.CacheGB = Cache.Value;
        C.Workers = (int)Workers.Value;
        C.Ahead = (int)Ahead.Value;
        C.Save();
        Labels();
        RestartText.Visibility = App.Server.IsRunning ? Visibility.Visible : Visibility.Collapsed;
    }

    void Toggle(object sender, RoutedEventArgs e)
    {
        C.Cdae = Cdae.IsChecked == true;
        C.StartServerWithGame = WithGame.IsChecked == true;
        C.StopServerWithGame = StopWithGame.IsChecked == true;
        C.StartServerWithApp = WithApp.IsChecked == true;
        C.UpdateServer = UpdateServer.IsChecked == true;
        C.Save();
        RestartText.Visibility = App.Server.IsRunning ? Visibility.Visible : Visibility.Collapsed;
    }

    void Lua_Click(object sender, RoutedEventArgs e)
    {
        if (!LuaOverrideInstalled()) { Ui.Main.Navigate("download"); return; }
        if (BeamNG.Running()) { Ui.Info("Close BeamNG first."); return; }
        try
        {
            Directory.Delete(LuaDir, true);
            Log.Write("server test Lua removed from the user folder");
        }
        catch (Exception ex) { Ui.Info(ex.Message); }
        Tick();
    }

    void OpenExe_Click(object sender, RoutedEventArgs e)
    {
        string? exe = PackManager.ServerExe(C);
        Ui.Open(exe is null ? App.Packs.ServerHome : Path.GetDirectoryName(exe));
    }

    void Copy_Click(object sender, RoutedEventArgs e)
    {
        try { Clipboard.SetText(LogBox.Text); } catch { }
    }

    void Clear_Click(object sender, RoutedEventArgs e) => LogBox.Clear();
}
