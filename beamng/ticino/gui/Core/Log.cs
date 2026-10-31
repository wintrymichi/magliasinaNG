namespace TicinoServer.Core;

/// <summary>The app's log (%LOCALAPPDATA%\TicinoServer\app.log, the last ~1 MB) and the lines the UI shows.</summary>
public static class Log
{
    static readonly object Gate = new();
    public static event Action<string>? Line;

    public static void Write(string text)
    {
        string line = $"{DateTime.Now:HH:mm:ss} {text}";
        lock (Gate)
        {
            try
            {
                Directory.CreateDirectory(AppConfig.Dir);
                string p = Path.Combine(AppConfig.Dir, "app.log");
                if (File.Exists(p) && new FileInfo(p).Length > 1_000_000)
                    File.Move(p, p + ".1", true);
                File.AppendAllText(p, line + Environment.NewLine);
            }
            catch { /* a log that cannot be written must not stop anything */ }
        }
        Line?.Invoke(line);
    }
}
