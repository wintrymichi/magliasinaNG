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
        var v = Assembly.GetExecutingAssembly().GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion ?? "";
        VersionText.Text = "Versione " + v;
    }

    void Repo_Click(object sender, RoutedEventArgs e) => Ui.Open("https://github.com/" + App.Config.Repo);

    void Readme_Click(object sender, RoutedEventArgs e) =>
        Ui.Open($"https://github.com/{App.Config.Repo}/blob/ticino/beamng/ticino/README.md");

    void Logs_Click(object sender, RoutedEventArgs e) => Ui.Open(AppConfig.Dir);
}
