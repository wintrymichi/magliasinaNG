using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using TicinoServer.Core;

namespace TicinoServer.Pages;

public partial class AboutPage : UserControl
{
    public AboutPage()
    {
        InitializeComponent();
        // "1.0.0+abc1234" (ticino_gui.yml) -> "Version 1.0.0 (abc1234)"; the first commit part only, if the SDK adds more
        var v = Assembly.GetExecutingAssembly().GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion ?? "";
        var parts = v.Split('+', StringSplitOptions.RemoveEmptyEntries);
        VersionText.Text = "Version " + (parts.Length > 1 ? $"{parts[0]} ({parts[1][..Math.Min(7, parts[1].Length)]})" : v);
    }

    void Repo_Click(object sender, RoutedEventArgs e) => Ui.Open("https://github.com/" + App.Config.Repo);

    void Readme_Click(object sender, RoutedEventArgs e) =>
        Ui.Open($"https://github.com/{App.Config.Repo}/blob/ticino/beamng/ticino/README.md");

    void Logs_Click(object sender, RoutedEventArgs e) => Ui.Open(AppConfig.Dir);
}
