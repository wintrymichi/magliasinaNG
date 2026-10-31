using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using TicinoServer.Core;

namespace TicinoServer.Pages;

public partial class DownloadPage : UserControl, ITickable
{
    readonly ICollectionView view;
    bool loading = true;
    string suggested = App.Packs.SuggestDataFolder();

    static PackManager P => App.Packs;
    static AppConfig C => App.Config;

    public DownloadPage()
    {
        InitializeComponent();
        view = CollectionViewSource.GetDefaultView(P.Items);
        view.Filter = o => OnlyPending.IsChecked != true || o is PackItem { State: not PackState.Installed };
        List.ItemsSource = view;
        TagBox.Text = C.Tag;
        CheckOnStart.IsChecked = C.CheckOnStart;
        AutoDownload.IsChecked = C.AutoDownload;
        DeleteOld.IsChecked = C.DeleteOld;
        foreach (ComboBoxItem i in Parallel.Items)
            if ((string)i.Content == C.ParallelDownloads.ToString()) Parallel.SelectedItem = i;
        if (Parallel.SelectedItem is null) Parallel.SelectedIndex = 2;
        loading = false;
        P.PropertyChanged += (_, _) => Dispatcher.BeginInvoke(Refresh);
        Refresh();
    }

    public void Tick() => Refresh();

    void Refresh()
    {
        var rel = P.Release;
        ReleaseTitle.Text = rel is null ? $"Release {C.Tag}" :
            $"{(string.IsNullOrWhiteSpace(rel.Name) ? rel.Tag : rel.Name)}{(rel.Draft ? " · draft" : "")}";
        SummaryText.Text = P.Checking ? "Reading the release on GitHub…" : P.Summary;
        LastCheckText.Text = C.LastCheck is { } t ? $"Last check: {t:d MMM yyyy HH:mm}" : "";
        ErrorBar.Visibility = P.Error != null ? Visibility.Visible : Visibility.Collapsed;
        ErrorBar.Message = P.Error ?? "";
        FolderBar.Visibility = P.DataFolder is null ? Visibility.Visible : Visibility.Collapsed;
        if (P.DataFolder is null && !P.Checking) suggested = P.SuggestDataFolder();
        FolderBar.Message = $"The zones take about 52 GB. Suggested: {suggested} ({Files.Size(Files.FreeSpace(suggested))} free).";
        string? why = P.ApplyBlocker();
        ReadyBar.Visibility = P.ReadyCount > 0 && !P.Busy ? Visibility.Visible : Visibility.Collapsed;
        ReadyBar.Message = why is null
            ? $"{P.ReadyCount} zips ready to install."
            : $"{P.ReadyCount} zips ready: they install themselves {(why.StartsWith("BeamNG") ? "when you close BeamNG" : "when the server stops")}.";
        ReadyBar.Severity = why is null ? "Info" : "Warning";

        DataCard.Description = P.DataFolder is null
            ? "Not chosen yet."
            : $"{P.DataFolder} · {Files.Size(Files.FreeSpace(P.DataFolder))} free";
        BaseCard.Description = $"{BeamNG.Mods(C)} (BeamNG's mods folder)";

        CheckButton.IsEnabled = !P.Checking && !P.Busy;
        DownloadButton.IsEnabled = P.Busy || (P.NeedCount > 0 && P.DataFolder != null && !P.Checking);
        DownloadLabel.Text = P.Busy ? "Pause" : P.Items.Any(i => i.State == PackState.Update) ? "Update" : "Download";
        DownloadGlyph.Text = P.Busy ? "" : "";
        ProgressPanel.Visibility = P.Busy || P.ProgressText.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
        Overall.Value = P.Overall;
        ProgressText.Text = P.ProgressText;
        EmptyText.Visibility = P.Items.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
    }

    async void Check_Click(object sender, RoutedEventArgs e) => await Ui.Main.CheckForUpdates(false);

    async void Download_Click(object sender, RoutedEventArgs e)
    {
        if (P.Busy) { P.Pause(); return; }
        await P.DownloadAll();
    }

    async void Apply_Click(object sender, RoutedEventArgs e)
    {
        string? why = P.ApplyBlocker();
        if (why == PackManager.ServerRunningReason && !BeamNG.Running() &&
            Ui.Ask("The server is running and keeps the zips open. Stop it, install the updates and start it again?"))
        {
            await App.Server.Stop();
            await P.ApplyPending();
            App.Server.Start();
            return;
        }
        if (why != null) { Ui.Info($"Not yet: {why}. The updates install themselves as soon as they can."); return; }
        await P.ApplyPending();
    }

    async void UseSuggested_Click(object sender, RoutedEventArgs e) => await SetData(suggested);

    async void ChangeData_Click(object sender, RoutedEventArgs e)
    {
        string? f = Ui.ChooseFolder("Folder for the Ticino zone packs", P.DataFolder ?? suggested);
        if (f != null) await SetData(f);
    }

    async Task SetData(string folder)
    {
        string? old = P.DataFolder;
        bool move = false;
        if (old != null && Directory.Exists(old) && Directory.EnumerateFiles(old, "ticino_*.zip").Any() &&
            !string.Equals(Path.GetFullPath(old), Path.GetFullPath(folder), StringComparison.OrdinalIgnoreCase))
            move = Ui.Ask($"Move the packs already downloaded from\n{old}\nto\n{folder}?\n\nIf you answer No they stay where they are and everything is downloaded again into the new folder.");
        try
        {
            IsEnabled = false;
            await P.ChangeDataFolder(old, folder, move, new Progress<string>(t => ProgressText.Text = "Moving: " + t));
        }
        catch (Exception ex) { Ui.Info(ex.Message); }
        finally { IsEnabled = true; ProgressText.Text = ""; }
        Refresh();
    }

    void OpenData_Click(object sender, RoutedEventArgs e) => Ui.Open(P.DataFolder);

    void Options_Click(object sender, RoutedEventArgs e)
    {
        C.CheckOnStart = CheckOnStart.IsChecked == true;
        C.AutoDownload = AutoDownload.IsChecked == true;
        C.DeleteOld = DeleteOld.IsChecked == true;
        C.Save();
    }

    void Parallel_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (loading || Parallel.SelectedItem is not ComboBoxItem i) return;
        C.ParallelDownloads = int.Parse((string)i.Content);
        C.Save();
    }

    async void Tag_LostFocus(object sender, RoutedEventArgs e) => await SetTag();

    async void Tag_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) await SetTag();
    }

    async Task SetTag()
    {
        string t = TagBox.Text.Trim();
        if (t.Length == 0 || t == C.Tag || P.Busy) { TagBox.Text = C.Tag; return; }
        C.Tag = t;
        C.Save();
        await P.Refresh();
    }

    void Filter_Click(object sender, RoutedEventArgs e) => view.Refresh();
}
