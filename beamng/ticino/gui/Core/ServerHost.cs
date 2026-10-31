using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

namespace TicinoServer.Core;

public enum ServerStatus { Stopped, Starting, Running, Stopping }

/// <summary>Runs ticino_server.exe (beamng/ticino/server) as a hidden child process, shows its output and reads its
/// state from the files it shares with the mod (temp\ticino\helper\alive.json, req.json). Stopped with Ctrl+C, so
/// it removes its files from the user folder as when stopped by hand.</summary>
public sealed class ServerHost : Observable
{
    readonly AppConfig cfg;
    Process? proc;
    readonly StringBuilder logText = new();
    const int LogMax = 200_000;

    public ServerHost(AppConfig cfg) { this.cfg = cfg; }

    public event Action<string>? Output;

    ServerStatus status;
    public ServerStatus Status
    {
        get => status;
        private set
        {
            if (Set(ref status, value))
            {
                Raise(nameof(IsRunning));
                Raise(nameof(StatusText));
            }
        }
    }

    public bool IsRunning => Status is ServerStatus.Running or ServerStatus.Starting or ServerStatus.Stopping;

    public string StatusText => Status switch
    {
        ServerStatus.Starting => "Starting…",
        ServerStatus.Running => Live ? "Running" : "Running (waiting for the game)",
        ServerStatus.Stopping => "Stopping…",
        _ => "Stopped",
    };

    public string LogText { get { lock (logText) return logText.ToString(); } }

    // live state from alive.json / req.json
    bool live;
    public bool Live { get => live; private set { if (Set(ref live, value)) Raise(nameof(StatusText)); } }
    long cacheMB;
    public long CacheMB { get => cacheMB; private set => Set(ref cacheMB, value); }
    int units;
    public int Units { get => units; private set => Set(ref units, value); }
    int pending;
    public int Pending { get => pending; private set => Set(ref pending, value); }
    int converted;
    public int Converted { get => converted; private set => Set(ref converted, value); }
    int windows;
    public int Windows { get => windows; private set => Set(ref windows, value); }
    string car = "";
    /// <summary>Where the game's car is (req.json, written by the mod every 250 ms while the level runs).</summary>
    public string Car { get => car; private set => Set(ref car, value); }
    bool gameConnected;
    public bool GameConnected { get => gameConnected; private set => Set(ref gameConnected, value); }

    public string? LastError { get; private set; }

    void Append(string line)
    {
        lock (logText)
        {
            logText.AppendLine(line);
            if (logText.Length > LogMax) logText.Remove(0, logText.Length - LogMax * 3 / 4);
        }
        Output?.Invoke(line);
    }

    /// <summary>Starts the server. Returns an error text, or null.</summary>
    public string? Start()
    {
        if (IsRunning) return null;
        string? exe = PackManager.ServerExe();
        if (exe is null) return "The server program is not downloaded yet (Downloads page).";
        if (string.IsNullOrWhiteSpace(cfg.DataFolder) || !Directory.Exists(cfg.DataFolder))
            return "The packs folder does not exist: choose it on the Downloads page.";
        if (!Directory.EnumerateFiles(cfg.DataFolder!, "ticino_*.zip").Any())
            return "The packs folder has no zones: download them on the Downloads page.";
        var psi = new ProcessStartInfo(exe)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            WorkingDirectory = Path.GetDirectoryName(exe)!,
        };
        psi.Environment["PYTHONUNBUFFERED"] = "1";
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        foreach (var a in new[]
                 {
                     "run", "--user", BeamNG.UserFolder(cfg), "--data", cfg.DataFolder!,
                     "--cache-gb", cfg.CacheGB.ToString(System.Globalization.CultureInfo.InvariantCulture),
                     "--workers", cfg.Workers.ToString(), "--ahead", Math.Clamp(cfg.Ahead, 1, 8).ToString(),
                 })
            psi.ArgumentList.Add(a);
        if (!cfg.Cdae) psi.ArgumentList.Add("--dae");
        try
        {
            var p = new Process { StartInfo = psi, EnableRaisingEvents = true };
            p.OutputDataReceived += (_, e) => { if (e.Data != null) Append(e.Data); };
            p.ErrorDataReceived += (_, e) => { if (e.Data != null) Append(e.Data); };
            p.Exited += (_, _) => OnExit(p);
            Status = ServerStatus.Starting;
            Append($"--- start: {exe} {string.Join(' ', psi.ArgumentList)}");
            p.Start();
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            proc = p;
            Log.Write($"server started (pid {p.Id})");
            return null;
        }
        catch (Exception e)
        {
            Status = ServerStatus.Stopped;
            LastError = e.Message;
            return "The server does not start: " + e.Message;
        }
    }

    void OnExit(Process p)
    {
        int code = -1;
        try { code = p.ExitCode; } catch { }
        Append($"--- server ended (exit code {code})");
        Log.Write($"server ended ({code})");
        if (ReferenceEquals(p, proc)) proc = null;
        CleanUp();
        Status = ServerStatus.Stopped;
        Live = false;
        GameConnected = false;
    }

    /// <summary>The files a server killed (not stopped) leaves in the user folder: the mod would wait for them.</summary>
    void CleanUp()
    {
        try
        {
            string h = BeamNG.HelperDir(cfg);
            foreach (var f in new[] { "alive.json", "ready.json" })
                if (File.Exists(Path.Combine(h, f))) File.Delete(Path.Combine(h, f));
            string srv = BeamNG.ServeDir(cfg);
            if (Directory.Exists(srv)) Directory.Delete(srv, true);
        }
        catch (Exception e) { Log.Write("clean-up: " + e.Message); }
    }

    [DllImport("kernel32.dll", SetLastError = true)] static extern bool AttachConsole(uint pid);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool FreeConsole();
    [DllImport("kernel32.dll")] static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
    [DllImport("kernel32.dll")] static extern bool GenerateConsoleCtrlEvent(uint ctrlEvent, uint groupId);

    static readonly SemaphoreSlim ConsoleGate = new(1, 1);

    /// <summary>Ctrl+C into the server's (hidden) console: Python stops with KeyboardInterrupt and cleans up.</summary>
    static async Task<bool> SendCtrlC(Process p)
    {
        await ConsoleGate.WaitAsync();
        try
        {
            if (!AttachConsole((uint)p.Id)) return false;
            SetConsoleCtrlHandler(IntPtr.Zero, true);       // this app ignores the Ctrl+C it sends
            bool ok = GenerateConsoleCtrlEvent(0, 0);
            FreeConsole();
            await Task.Delay(500);
            SetConsoleCtrlHandler(IntPtr.Zero, false);
            return ok;
        }
        finally { ConsoleGate.Release(); }
    }

    public async Task Stop()
    {
        var p = proc;
        if (p is null || p.HasExited) { Status = ServerStatus.Stopped; return; }
        Status = ServerStatus.Stopping;
        Append("--- stopping (Ctrl+C)");
        bool sent = false;
        try { sent = await SendCtrlC(p); } catch (Exception e) { Log.Write("Ctrl+C: " + e.Message); }
        var waited = Task.Run(() => p.WaitForExit(sent ? 15_000 : 0));
        if (!await waited)
        {
            Append("--- the server does not stop: killed");
            try { p.Kill(true); } catch { }
            await Task.Run(() => p.WaitForExit(5_000));
            CleanUp();
        }
    }

    /// <summary>Stops the server at once (the app closes).</summary>
    public void StopNow()
    {
        var p = proc;
        if (p is null) return;
        try
        {
            if (!p.HasExited)
            {
                SendCtrlC(p).Wait(2_000);
                if (!p.WaitForExit(8_000)) p.Kill(true);
            }
        }
        catch { }
        CleanUp();
    }

    /// <summary>Reads alive.json and req.json (once a second from the UI's timer).</summary>
    public void Poll()
    {
        if (Status == ServerStatus.Starting && proc is { HasExited: false }) Status = ServerStatus.Running;
        string dir = BeamNG.HelperDir(cfg);
        try
        {
            string a = Path.Combine(dir, "alive.json");
            if (IsRunning && File.Exists(a))
            {
                using var d = JsonDocument.Parse(File.ReadAllText(a));
                var r = d.RootElement;
                double t = r.TryGetProperty("t", out var tv) ? tv.GetDouble() : 0;
                Live = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0 - t < 5;
                CacheMB = r.TryGetProperty("cacheMB", out var c) ? c.GetInt64() : 0;
                Units = r.TryGetProperty("units", out var u) ? u.GetInt32() : 0;
                Pending = r.TryGetProperty("pending", out var pe) ? pe.GetInt32() : 0;
                Converted = r.TryGetProperty("converted", out var cv) ? cv.GetInt32() : 0;
                Windows = r.TryGetProperty("ready", out var w) && w.ValueKind == JsonValueKind.Number ? w.GetInt32() : 0;
            }
            else Live = false;
            string q = Path.Combine(dir, "req.json");
            if (File.Exists(q) && DateTime.UtcNow - File.GetLastWriteTimeUtc(q) < TimeSpan.FromSeconds(5))
            {
                using var d = JsonDocument.Parse(File.ReadAllText(q));
                var r = d.RootElement;
                double x = r.GetProperty("x").GetDouble(), y = r.GetProperty("y").GetDouble();
                double vx = r.TryGetProperty("vx", out var a1) ? a1.GetDouble() : 0;
                double vy = r.TryGetProperty("vy", out var a2) ? a2.GetDouble() : 0;
                double kmh = Math.Sqrt(vx * vx + vy * vy) * 3.6;
                Car = $"car at x {x:0}, y {y:0} · {kmh:0} km/h";
                GameConnected = true;
            }
            else
            {
                Car = "";
                GameConnected = false;
            }
        }
        catch { /* a file being replaced: next second */ }
    }
}
