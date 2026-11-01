using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;

namespace TicinoServer.Core;

/// <summary>The app updates itself from app_ticino.zip on GitHub: the map's release, else the public pre-release where
/// the app is published (draft map builds carry no app). The version is read from the VERSION.txt inside the zip
/// ("version 1.1.3") with a few HTTP range requests, so a check downloads kilobytes, not the 55 MB zip. The PC test of
/// 2026-11-01 found michi's copy in Downloads still at an old version after three releases: nothing told him.</summary>
public sealed class AppUpdate : Observable
{
    public const string AssetName = "app_ticino.zip";
    static readonly string[] AppReleases = { "ticino-v1" };

    readonly GitHub gh = new();
    ReleaseAsset? asset;

    /// <summary>This app's version (three parts: 1.1.2.0 and 1.1.2 must compare equal).</summary>
    public static Version Current { get; } = Three(typeof(AppUpdate).Assembly.GetName().Version);

    public Version? Available { get => available; private set { if (Set(ref available, value)) Raise(nameof(IsAvailable)); } }
    Version? available;

    public bool IsAvailable => Available != null && Available > Current;

    public bool Busy { get => busy; private set => Set(ref busy, value); }
    bool busy;

    /// <summary>Progress or error of the last update.</summary>
    public string Text { get => text; private set => Set(ref text, value); }
    string text = "";

    static Version Three(Version? v) => v is null ? new Version(0, 0, 0) : new Version(v.Major, v.Minor, Math.Max(0, v.Build));

    /// <summary>Looks for a newer app; never throws (a failed check only leaves a log line).</summary>
    public async Task Check(AppConfig cfg, Release? map)
    {
        try
        {
            var a = map?.Assets.FirstOrDefault(x => x.Name == AssetName);
            foreach (var t in AppReleases)
            {
                if (a != null) break;
                if (t == map?.Tag) continue;
                var r = await gh.GetRelease(cfg.Repo, t, CancellationToken.None);
                a = r.Assets.FirstOrDefault(x => x.Name == AssetName);
            }
            if (a is null) return;
            string? v = await Task.Run(() => RemoteVersion(a));
            // a build before 1.1.3 names no version in VERSION.txt: never offered (it is not newer anyway)
            if (v is null || !Version.TryParse(v, out var ver)) return;
            asset = a;
            Available = Three(ver);
            if (IsAvailable) Log.Write($"Ticino Server {Available} is available on GitHub (this is {Current})");
        }
        catch (Exception e) { Log.Write("app update check: " + e.Message); }
    }

    /// <summary>The "version" line of VERSION.txt inside the zip on the release, read by range requests.</summary>
    public string? RemoteVersion(ReleaseAsset a)
    {
        using var s = new RangeStream(a.Size, (from, to) => gh.ReadRange(a, from, to));
        return VersionIn(s);
    }

    /// <summary>The "version" line of VERSION.txt in a zip (a file, or a range stream on the release).</summary>
    public static string? VersionIn(Stream zip)
    {
        using var z = new ZipArchive(zip, ZipArchiveMode.Read, leaveOpen: true);
        var e = z.GetEntry("VERSION.txt");
        if (e is null) return null;
        using var r = new StreamReader(e.Open());
        foreach (var line in r.ReadToEnd().Split('\n'))
            if (line.StartsWith("version ", StringComparison.Ordinal)) return line[8..].Trim();
        return null;
    }

    /// <summary>Why the app cannot replace itself now, or null.</summary>
    public static string? Blocker()
    {
        if (BeamNG.Running()) return "Close BeamNG first.";
        if (App.Server.IsRunning) return "Stop the server first (Home).";
        if (App.Packs.Busy || App.Packs.Moving) return "Wait for the download or the move to end (or pause it) first.";
        return null;
    }

    /// <summary>Downloads the new app, checks its sha256, and leaves a small script that waits for this process to
    /// end, copies the new exe over this one and starts it. Returns true when the caller should close the app.</summary>
    public async Task<bool> Install()
    {
        if (asset is null || Busy) return false;
        string exe = Environment.ProcessPath ?? "";
        string dir = Path.Combine(AppConfig.Dir, "update");
        Busy = true;
        try
        {
            if (!File.Exists(exe)) throw new InvalidOperationException("this exe was not found on disk");
            // the folder of the exe must take a new file (not Program Files without admin rights)
            string probe = Path.Combine(Path.GetDirectoryName(exe)!, ".ticino_update_probe");
            File.WriteAllText(probe, "");
            File.Delete(probe);

            Directory.CreateDirectory(dir);
            string zip = Path.Combine(dir, AssetName);
            using (var r = await gh.OpenAsset(asset, 0, CancellationToken.None))
            await using (var src = await r.Content.ReadAsStreamAsync())
            await using (var dst = File.Create(zip))
            {
                var buf = new byte[1 << 20];
                long done = 0;
                int n;
                while ((n = await src.ReadAsync(buf)) > 0)
                {
                    await dst.WriteAsync(buf.AsMemory(0, n));
                    done += n;
                    Text = $"Downloading Ticino Server {Available}: {Files.Size(done)} of {Files.Size(asset.Size)}";
                }
            }
            if (asset.Sha256 is { } want)
            {
                await using var f = File.OpenRead(zip);
                string got = Convert.ToHexString(await SHA256.HashDataAsync(f)).ToLowerInvariant();
                if (got != want) throw new InvalidDataException("the download does not match the release (sha256)");
            }
            string fresh = Path.Combine(dir, "TicinoServer.exe");
            using (var z = ZipFile.OpenRead(zip))
            {
                var e = z.GetEntry("TicinoServer.exe") ?? throw new InvalidDataException($"no TicinoServer.exe in {AssetName}");
                e.ExtractToFile(fresh, true);
            }
            File.Delete(zip);

            // cmd waits for this process (a running exe cannot be overwritten), copies with a few tries, starts it
            string cmd = Path.Combine(dir, "update.cmd");
            int pid = Environment.ProcessId;
            File.WriteAllText(cmd, string.Join("\r\n",
                "@echo off",
                ":wait",
                $"tasklist /fi \"PID eq {pid}\" /nh | find \"{pid}\" >nul && (ping -n 2 127.0.0.1 >nul & goto wait)",
                "set n=0",
                ":copy",
                $"copy /y \"{fresh}\" \"{exe}\" >nul && goto start",
                "set /a n+=1",
                "if %n% geq 15 goto start",
                "ping -n 2 127.0.0.1 >nul",
                "goto copy",
                ":start",
                $"start \"\" \"{exe}\" --after-update",
                "") );
            Process.Start(new ProcessStartInfo("cmd.exe", $"/c \"{cmd}\"")
            {
                UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = dir,
            });
            Log.Write($"app update to {Available} downloaded: the app closes and starts again");
            Text = "Restarting…";
            return true;
        }
        catch (Exception e)
        {
            Log.Write("app update failed: " + e.Message);
            Text = "The update failed: " + e.Message;
            return false;
        }
        finally { Busy = false; }
    }

    /// <summary>After an update: the downloaded copy is not needed any more.</summary>
    public static void CleanUp(bool afterUpdate)
    {
        string dir = Path.Combine(AppConfig.Dir, "update");
        if (afterUpdate) Log.Write($"updated to Ticino Server {Current}");
        try { if (Directory.Exists(dir)) Directory.Delete(dir, true); }
        catch { /* the script may still be closing: next start */ }
    }
}

/// <summary>A read-only seekable view of a remote file through a fetch(from, to) of byte ranges, with one cached block:
/// enough for ZipArchive to read the central directory at the end and one small entry (two or three requests).</summary>
sealed class RangeStream : Stream
{
    const int Block = 1 << 16;
    readonly long length;
    readonly Func<long, long, byte[]> fetch;
    long pos, start = -1;
    byte[] block = Array.Empty<byte>();

    public RangeStream(long length, Func<long, long, byte[]> fetch)
    {
        this.length = length;
        this.fetch = fetch;
    }

    public override bool CanRead => true;
    public override bool CanSeek => true;
    public override bool CanWrite => false;
    public override long Length => length;
    public override long Position { get => pos; set => pos = value; }

    public override int Read(byte[] buffer, int offset, int count)
    {
        if (pos >= length || count <= 0) return 0;
        if (start < 0 || pos < start || pos >= start + block.Length)
        {
            // half a block behind the position too: ZipArchive reads the end of the zip backwards
            start = Math.Max(0, pos - Block / 2);
            long end = Math.Min(length, Math.Max(start + Block, pos + count)) - 1;
            block = fetch(start, end);
            if (pos >= start + block.Length) return 0;
        }
        int n = (int)Math.Min(count, start + block.Length - pos);
        Array.Copy(block, pos - start, buffer, offset, n);
        pos += n;
        return n;
    }

    public override long Seek(long offset, SeekOrigin origin)
    {
        pos = origin switch { SeekOrigin.Begin => offset, SeekOrigin.Current => pos + offset, _ => length + offset };
        return pos;
    }

    public override void Flush() { }
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
}
