using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using TicinoServer.Core;

namespace TicinoServer.Pages;

public partial class GraphicsPage : UserControl
{
    GameSettings s;
    bool loading;
    readonly DispatcherTimer save = new() { Interval = TimeSpan.FromMilliseconds(600) };
    readonly DispatcherTimer hideSaved = new() { Interval = TimeSpan.FromSeconds(4) };

    string FilePath => BeamNG.SettingsFile(App.Config);

    public GraphicsPage()
    {
        InitializeComponent();
        s = GameSettings.Load(FilePath);
        save.Tick += (_, _) => { save.Stop(); Save(); };
        hideSaved.Tick += (_, _) => { hideSaved.Stop(); SavedBar.Visibility = Visibility.Collapsed; };
        Show();
    }

    static string Tiles(int n) => n == 0 ? "only the car's tile" : $"{Files.Metres(n * GameSettings.TileM + GameSettings.TileM / 2)}";

    void Show()
    {
        loading = true;
        Forest.Value = s.ForestRadius;
        Far.Value = s.FarRadius;
        Buildings.Value = s.Buildings;
        Roads.Value = s.Roads;
        Details.Value = s.Details;
        BurstEvery.Value = s.BurstEveryMs;
        Burst.Value = s.BurstMs;
        Block.Value = s.ForestBlock;
        Hyst.Value = s.ForestHyst;
        Helper.IsChecked = s.Helper;
        Diagnostics.IsChecked = s.Diagnostics;
        foreach (ComboBoxItem i in QualityBox.Items)
            if ((string)i.Tag == s.Quality.ToString()) QualityBox.SelectedItem = i;
        Labels();
        loading = false;
    }

    void Labels()
    {
        ForestText.Text = Tiles(s.ForestRadius);
        FarText.Text = Tiles(s.FarRadius);
        BuildingsText.Text = Tiles(s.Buildings);
        RoadsText.Text = Tiles(s.Roads);
        DetailsText.Text = s.Details switch { 0 => "near", 1 => "normal", _ => "far" };
        BurstEveryText.Text = $"{s.BurstEveryMs} ms";
        BurstText.Text = $"{s.BurstMs} ms";
        BlockText.Text = $"{s.ForestBlock} x {s.ForestBlock}";
        HystText.Text = s.ForestHyst.ToString();
    }

    void Slider_Changed(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (loading || s is null) return;
        s.ForestRadius = (int)Forest.Value;
        s.FarRadius = (int)Far.Value;
        s.Buildings = (int)Buildings.Value;
        s.Roads = (int)Roads.Value;
        s.Details = (int)Details.Value;
        s.BurstEveryMs = (int)BurstEvery.Value;
        s.BurstMs = (int)Burst.Value;
        s.ForestBlock = (int)Block.Value;
        s.ForestHyst = (int)Hyst.Value;
        if (sender == Forest || sender == Far || sender == Buildings || sender == Roads || sender == Details)
        {
            s.Quality = s.Match();
            loading = true;
            foreach (ComboBoxItem i in QualityBox.Items)
                if ((string)i.Tag == s.Quality.ToString()) QualityBox.SelectedItem = i;
            loading = false;
        }
        Labels();
        Changed();
    }

    void Toggle_Changed(object sender, RoutedEventArgs e)
    {
        if (loading || s is null) return;
        s.Helper = Helper.IsChecked == true;
        s.Diagnostics = Diagnostics.IsChecked == true;
        Changed();
    }

    void Quality_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (loading || s is null || QualityBox.SelectedItem is not ComboBoxItem i) return;
        var q = Enum.Parse<Quality>((string)i.Tag);
        if (q == Quality.Custom) { s.Quality = q; Changed(); return; }
        var p = GameSettings.Preset(q);
        p.Helper = s.Helper;
        p.Diagnostics = s.Diagnostics;
        p.BurstEveryMs = s.BurstEveryMs;
        p.BurstMs = s.BurstMs;
        p.ForestBlock = s.ForestBlock;
        p.ForestHyst = s.ForestHyst;
        s = p;
        Show();
        Changed();
    }

    void Changed()
    {
        save.Stop();
        save.Start();
    }

    void Save()
    {
        try
        {
            s.Save(FilePath);
            SavedBar.Severity = "Success";
            SavedBar.Title = "Saved";
            SavedBar.Message = BeamNG.Running()
                ? "BeamNG is open: the settings apply the next time you load the map."
                : "They apply the next time the map loads.";
        }
        catch (Exception ex)
        {
            SavedBar.Severity = "Error";
            SavedBar.Title = "Not saved";
            SavedBar.Message = $"{FilePath}: {ex.Message}";
        }
        SavedBar.Visibility = Visibility.Visible;
        hideSaved.Stop();
        hideSaved.Start();
    }

    void Reset_Click(object sender, RoutedEventArgs e)
    {
        s = GameSettings.Preset(Quality.High);
        Show();
        Changed();
    }

    void OpenFile_Click(object sender, RoutedEventArgs e)
    {
        if (!File.Exists(FilePath)) Save();
        Ui.Open(FilePath);
    }
}
