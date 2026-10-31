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
    static string LuaSource => Path.Combine(PackManager.ServerDir, "lua", "ge", "extensions", "ticino");

    /// <summary>Is the server's test Lua in the user folder (it overrides the base pack's)?</summary>
    public static bool LuaOverrideInstalled() => File.Exists(Path.Combine(LuaDir, "files.lua"));

    public void Tick()
    {
        bool? baseLua = App.Packs.BaseHasServerLua();
        bool have = LuaOverrideInstalled();
        LuaBar.Visibility = baseLua == false || have ? Visibility.Visible : Visibility.Collapsed;
        if (have)
        {
            LuaBar.Severity = baseLua == true ? "Warning" : "Info";
            LuaBar.Message = baseLua == true
                ? "The base pack now has the server Lua: remove the test one from the user folder, or it hides the new Lua."
                : "Installed in the BeamNG user folder: it takes the place of the base pack's Lua until a base pack that knows the server is out.";
            LuaButton.Content = "Remove";
        }
        else
        {
            LuaBar.Severity = "Warning";
            LuaBar.Message = Directory.Exists(LuaSource)
                ? "The installed base pack loads zones from mods only. To try the server, its Lua is needed in the BeamNG user folder (lua\\ge\\extensions\\ticino)."
                : "The installed base pack loads zones from mods only, and the server program is not downloaded yet.";
            LuaButton.Content = "Install";
            LuaButton.IsEnabled = Directory.Exists(LuaSource);
        }
        string? exe = PackManager.ServerExe();
        ExeCard.Description = exe ?? "Not downloaded yet (Downloads page).";
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
        if (BeamNG.Running()) { Ui.Info("Close BeamNG first."); return; }
        try
        {
            if (LuaOverrideInstalled())
            {
                Directory.Delete(LuaDir, true);
                Log.Write("server test Lua removed from the user folder");
            }
            else
            {
                if (!Ui.Ask("Copy the server test Lua to\n" + LuaDir + "?\n\nIt takes the place of the base pack's Lua. Remove it here with Remove (the classic installer also moves it away).")) return;
                Directory.CreateDirectory(LuaDir);
                foreach (var f in Directory.EnumerateFiles(LuaSource, "*.lua"))
                    File.Copy(f, Path.Combine(LuaDir, Path.GetFileName(f)), true);
                Log.Write("server test Lua copied into the user folder");
            }
        }
        catch (Exception ex) { Ui.Info(ex.Message); }
        Tick();
    }

    void OpenExe_Click(object sender, RoutedEventArgs e)
    {
        string? exe = PackManager.ServerExe();
        Ui.Open(exe is null ? PackManager.ServerDir : Path.GetDirectoryName(exe));
    }

    void Copy_Click(object sender, RoutedEventArgs e)
    {
        try { Clipboard.SetText(LogBox.Text); } catch { }
    }

    void Clear_Click(object sender, RoutedEventArgs e) => LogBox.Clear();
}
