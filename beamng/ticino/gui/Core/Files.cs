using System.Globalization;

namespace TicinoServer.Core;

public static class Files
{
    /// <summary>Writes a file under a temporary name and renames it: a reader (the game, the server) never sees half
    /// of it.</summary>
    public static void WriteAtomic(string path, string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string tmp = path + ".tmp";
        File.WriteAllText(tmp, text);          // UTF-8 without BOM: the game's JSON reader wants none
        File.Move(tmp, path, true);
    }

    public static readonly CultureInfo Culture = CultureInfo.GetCultureInfo("en-GB");

    public static string Size(double bytes)
    {
        if (bytes >= 1e9) return (bytes / 1e9).ToString("0.0", Culture) + " GB";
        if (bytes >= 1e6) return (bytes / 1e6).ToString("0", Culture) + " MB";
        if (bytes >= 1e3) return (bytes / 1e3).ToString("0", Culture) + " kB";
        return bytes.ToString("0", Culture) + " B";
    }

    public static string Speed(double bytesPerSecond) => Size(bytesPerSecond) + "/s";

    public static string Duration(TimeSpan t)
    {
        if (t.TotalHours >= 1) return $"{(int)t.TotalHours} h {t.Minutes:00} min";
        if (t.TotalMinutes >= 1) return $"{(int)t.TotalMinutes} min";
        return $"{Math.Max(1, (int)t.TotalSeconds)} s";
    }

    public static string Metres(double m) =>
        m >= 1000 ? (m / 1000).ToString("0.0", Culture) + " km" : m.ToString("0", Culture) + " m";

    /// <summary>Free bytes on the drive of a folder (the folder may not exist yet).</summary>
    public static long FreeSpace(string folder)
    {
        try
        {
            string? root = Path.GetPathRoot(Path.GetFullPath(folder));
            return root is null ? 0 : new DriveInfo(root).AvailableFreeSpace;
        }
        catch { return 0; }
    }

    public static bool SameDrive(string a, string b) =>
        string.Equals(Path.GetPathRoot(Path.GetFullPath(a)), Path.GetPathRoot(Path.GetFullPath(b)),
            StringComparison.OrdinalIgnoreCase);

    public static long FolderSize(string folder)
    {
        long n = 0;
        try
        {
            if (!Directory.Exists(folder)) return 0;
            foreach (var f in new DirectoryInfo(folder).EnumerateFiles("*", SearchOption.AllDirectories))
                n += f.Length;
        }
        catch { /* files come and go while the server runs */ }
        return n;
    }

    /// <summary>Moves a file, also to another drive (copy, then delete), reporting the bytes copied.</summary>
    public static async Task MoveAsync(string src, string dst, IProgress<long>? progress, CancellationToken ct)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(dst)!);
        if (SameDrive(src, dst))
        {
            File.Move(src, dst, true);
            progress?.Report(new FileInfo(dst).Length);
            return;
        }
        string tmp = dst + ".part";
        await using (var i = new FileStream(src, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20, true))
        await using (var o = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20, true))
        {
            var buf = new byte[1 << 20];
            int n;
            while ((n = await i.ReadAsync(buf, ct)) > 0)
            {
                await o.WriteAsync(buf.AsMemory(0, n), ct);
                progress?.Report(n);
            }
        }
        File.Move(tmp, dst, true);
        File.Delete(src);
    }
}
