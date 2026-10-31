using System.Diagnostics;
using System.Windows;
using Microsoft.Win32;

namespace TicinoServer;

static class Ui
{
    public static string? ChooseFolder(string title, string? start)
    {
        var d = new OpenFolderDialog { Title = title, Multiselect = false };
        if (!string.IsNullOrWhiteSpace(start) && Directory.Exists(start)) d.InitialDirectory = start;
        return d.ShowDialog(Application.Current.MainWindow) == true ? d.FolderName : null;
    }

    public static void Open(string? pathOrUrl)
    {
        if (string.IsNullOrWhiteSpace(pathOrUrl)) return;
        try
        {
            if (!pathOrUrl.StartsWith("http") && !Directory.Exists(pathOrUrl) && !File.Exists(pathOrUrl))
            {
                Info("La cartella non esiste ancora:\n" + pathOrUrl);
                return;
            }
            Process.Start(new ProcessStartInfo(pathOrUrl) { UseShellExecute = true });
        }
        catch (Exception e) { Info(e.Message); }
    }

    public static void Info(string text) =>
        MessageBox.Show(Application.Current.MainWindow!, text, "Ticino Server", MessageBoxButton.OK, MessageBoxImage.Information);

    public static bool Ask(string text) =>
        MessageBox.Show(Application.Current.MainWindow!, text, "Ticino Server", MessageBoxButton.YesNo, MessageBoxImage.Question)
        == MessageBoxResult.Yes;

    public static MainWindow Main => (MainWindow)Application.Current.MainWindow!;
}
