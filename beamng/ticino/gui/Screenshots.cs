using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using TicinoServer.Core;

namespace TicinoServer;

/// <summary>`TicinoServer.exe --screenshots <folder>`: every page in the light and the dark theme as PNG, then exit.
/// The build workflow runs it so the pages can be looked at without a Windows PC.</summary>
static class Screenshots
{
    static readonly string[] Pages = { "home", "graphics", "download", "server", "about" };

    static Task Idle() => Application.Current.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle).Task;

    public static async Task Run(MainWindow w, string folder)
    {
        int code = 0;
        try
        {
            Directory.CreateDirectory(folder);
            w.Width = 1200;
            w.Height = 820;
            w.WindowStartupLocation = WindowStartupLocation.Manual;
            w.Left = 0;
            w.Top = 0;
            w.Show();
            await Idle();
            await App.Packs.Refresh();
            foreach (var theme in new[] { ThemeMode.Light, ThemeMode.Dark })
            {
                Application.Current.ThemeMode = theme;
                foreach (var p in Pages)
                {
                    w.Navigate(p);
                    await Task.Delay(400);
                    await Idle();
                    string name = $"{p}_{(theme == ThemeMode.Dark ? "dark" : "light")}.png";
                    Save(w, Path.Combine(folder, name));
                    if (FullPage(w) is { } full)
                        Render(full, Path.Combine(folder, $"{p}_full_{(theme == ThemeMode.Dark ? "dark" : "light")}.png"), w);
                    Console.WriteLine("shot " + name);
                }
            }
        }
        catch (Exception e)
        {
            File.WriteAllText(Path.Combine(folder, "error.txt"), e.ToString());
            code = 1;
        }
        Application.Current.Shutdown(code);
    }

    /// <summary>The whole scrolled content of the page shown (for a look at what lies below the window).</summary>
    static FrameworkElement? FullPage(MainWindow w)
    {
        var page = (w.FindName("Page") as System.Windows.Controls.ContentControl)?.Content as System.Windows.Controls.UserControl;
        return (page?.Content as System.Windows.Controls.ScrollViewer)?.Content as FrameworkElement;
    }

    static void Save(Window w, string path) => Render((FrameworkElement)w.Content, path, w);

    static void Render(FrameworkElement root, string path, Window w)
    {
        double dpi = 96 * 1.25;
        int pw = (int)(root.ActualWidth * dpi / 96), ph = (int)(root.ActualHeight * dpi / 96);
        var bg = w.TryFindResource("SolidBackgroundFillColorBaseBrush") as Brush
                 ?? (Application.Current.ThemeMode == ThemeMode.Dark ? Brushes.Black : Brushes.White);
        var dv = new DrawingVisual();
        using (var dc = dv.RenderOpen())
        {
            dc.DrawRectangle(bg, null, new Rect(0, 0, root.ActualWidth, root.ActualHeight));
            dc.DrawRectangle(new VisualBrush(root), null, new Rect(0, 0, root.ActualWidth, root.ActualHeight));
        }
        var bmp = new RenderTargetBitmap(pw, ph, dpi, dpi, PixelFormats.Pbgra32);
        bmp.Render(dv);
        var enc = new PngBitmapEncoder();
        enc.Frames.Add(BitmapFrame.Create(bmp));
        using var f = File.Create(path);
        enc.Save(f);
    }
}
