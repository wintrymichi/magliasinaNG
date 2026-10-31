using System.Text.Json;
using System.Text.Json.Serialization;

namespace TicinoServer.Core;

/// <summary>The app's own settings (%LOCALAPPDATA%\TicinoServer\settings.json). The game's settings are in
/// <see cref="GameSettings"/> (settings\ticino.json of the BeamNG user folder), the server's in ticino_server.json.</summary>
public sealed class AppConfig
{
    public string Repo { get; set; } = "wintrymichi/magliasinaNG";
    public string Tag { get; set; } = "ticino-v1";             // the public pre-release (ticino_publish.yml)
    public string? DataFolder { get; set; }
    public string? UserFolder { get; set; }
    public string? GameFolder { get; set; }

    public bool CheckOnStart { get; set; } = true;
    // off until the user turns it on: a first start must never begin a 52 GB download by itself
    public bool AutoDownload { get; set; } = false;
    public bool DeleteOld { get; set; } = false;
    public int ParallelDownloads { get; set; } = 3;

    public double CacheGB { get; set; } = 8;
    public int Workers { get; set; } = Math.Max(1, Math.Min(6, Environment.ProcessorCount - 2));
    public int Ahead { get; set; } = 8;
    public bool Cdae { get; set; } = true;

    public bool StartServerWithApp { get; set; } = false;
    public bool StartServerWithGame { get; set; } = true;
    public bool StopServerWithGame { get; set; } = true;
    public bool UpdateServer { get; set; } = true;

    public DateTime? LastCheck { get; set; }

    static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public static string Dir =>
        Environment.GetEnvironmentVariable("TICINO_APP_DIR") is { Length: > 0 } d
            ? d
            : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TicinoServer");

    static string FilePath => Path.Combine(Dir, "settings.json");

    /// <summary>Has the app saved its settings on this PC before (false on the first start)?</summary>
    public static bool Exists => File.Exists(FilePath);

    public static AppConfig Load()
    {
        try
        {
            if (File.Exists(FilePath))
                return JsonSerializer.Deserialize<AppConfig>(File.ReadAllText(FilePath), Json) ?? new AppConfig();
        }
        catch (Exception e)
        {
            Log.Write($"settings.json not readable ({e.Message}): defaults");
        }
        return new AppConfig();
    }

    public void Save()
    {
        Directory.CreateDirectory(Dir);
        Files.WriteAtomic(FilePath, JsonSerializer.Serialize(this, Json));
        // the same settings for the server Start Ticino runs (ticino_server.json beside it)
        Installer.Sync(this, PackManager.OwnServerDir);
    }
}
