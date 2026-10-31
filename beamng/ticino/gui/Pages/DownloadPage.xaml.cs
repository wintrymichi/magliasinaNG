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
    string suggested = PackManager.SuggestDataFolder();

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
            $"{(string.IsNullOrWhiteSpace(rel.Name) ? rel.Tag : rel.Name)}{(rel.Draft ? " · bozza" : "")}";
        SummaryText.Text = P.Checking ? "Lettura della release su GitHub…" : P.Summary;
        LastCheckText.Text = C.LastCheck is { } t ? $"Ultimo controllo: {t:dd.MM.yyyy HH:mm}" : "";
        ErrorBar.Visibility = P.Error != null ? Visibility.Visible : Visibility.Collapsed;
        ErrorBar.Message = P.Error ?? "";
        FolderBar.Visibility = P.DataFolder is null ? Visibility.Visible : Visibility.Collapsed;
        FolderBar.Message = $"Le zone occupano circa 52 GB. Proposta: {suggested} ({Files.Size(Files.FreeSpace(suggested))} liberi).";
        string? why = P.ApplyBlocker();
        ReadyBar.Visibility = P.ReadyCount > 0 && !P.Busy ? Visibility.Visible : Visibility.Collapsed;
        ReadyBar.Message = why is null
            ? $"{P.ReadyCount} zip pronti da installare."
            : $"{P.ReadyCount} zip pronti: si installano da soli {(why.StartsWith("BeamNG") ? "quando chiudi BeamNG" : "quando il server si ferma")}.";
        ReadyBar.Severity = why is null ? "Info" : "Warning";

        DataCard.Description = P.DataFolder is null
            ? "Non ancora scelta."
            : $"{P.DataFolder} · {Files.Size(Files.FreeSpace(P.DataFolder))} liberi";
        BaseCard.Description = $"{BeamNG.Mods(C)} (la cartella mods di BeamNG)";

        CheckButton.IsEnabled = !P.Checking && !P.Busy;
        DownloadButton.IsEnabled = P.Busy || (P.NeedCount > 0 && P.DataFolder != null && !P.Checking);
        DownloadLabel.Text = P.Busy ? "Pausa" : P.Items.Any(i => i.State == PackState.Update) ? "Aggiorna" : "Scarica";
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
        if (why == "il server è in esecuzione" && !BeamNG.Running() &&
            Ui.Ask("Il server è in esecuzione e tiene aperti gli zip. Fermarlo, installare gli aggiornamenti e riavviarlo?"))
        {
            await App.Server.Stop();
            await P.ApplyPending();
            App.Server.Start();
            return;
        }
        if (why != null) { Ui.Info($"Non ancora: {why}. Gli aggiornamenti si installano da soli appena possibile."); return; }
        await P.ApplyPending();
    }

    async void UseSuggested_Click(object sender, RoutedEventArgs e) => await SetData(suggested);

    async void ChangeData_Click(object sender, RoutedEventArgs e)
    {
        string? f = Ui.ChooseFolder("Cartella dei pacchetti zona del Ticino", P.DataFolder ?? suggested);
        if (f != null) await SetData(f);
    }

    async Task SetData(string folder)
    {
        string? old = P.DataFolder;
        bool move = false;
        if (old != null && Directory.Exists(old) && Directory.EnumerateFiles(old, "ticino_*.zip").Any() &&
            !string.Equals(Path.GetFullPath(old), Path.GetFullPath(folder), StringComparison.OrdinalIgnoreCase))
            move = Ui.Ask($"Spostare i pacchetti già scaricati da\n{old}\na\n{folder}?\n\nSe rispondi No restano dove sono e nella nuova cartella si scarica tutto di nuovo.");
        try
        {
            IsEnabled = false;
            await P.ChangeDataFolder(old, folder, move, new Progress<string>(t => ProgressText.Text = "Spostamento: " + t));
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
