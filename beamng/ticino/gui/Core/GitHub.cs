using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TicinoServer.Core;

public sealed class ReleaseAsset
{
    [JsonPropertyName("id")] public long Id { get; set; }
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("size")] public long Size { get; set; }
    [JsonPropertyName("digest")] public string? Digest { get; set; }
    [JsonPropertyName("url")] public string ApiUrl { get; set; } = "";
    [JsonPropertyName("browser_download_url")] public string BrowserUrl { get; set; } = "";
    [JsonPropertyName("updated_at")] public DateTime Updated { get; set; }

    /// <summary>The sha256 GitHub keeps for the asset (lower case hex), or null.</summary>
    public string? Sha256 => Digest is { } d && d.StartsWith("sha256:") ? d[7..].ToLowerInvariant() : null;
}

public sealed class Release
{
    [JsonPropertyName("id")] public long Id { get; set; }
    [JsonPropertyName("tag_name")] public string Tag { get; set; } = "";
    [JsonPropertyName("name")] public string? Name { get; set; }
    [JsonPropertyName("draft")] public bool Draft { get; set; }
    [JsonPropertyName("prerelease")] public bool Prerelease { get; set; }
    [JsonPropertyName("published_at")] public DateTime? Published { get; set; }
    [JsonIgnore] public List<ReleaseAsset> Assets { get; set; } = new();
}

/// <summary>GitHub releases by the REST API. A draft release is found only with a token: GH_TOKEN, else the GitHub
/// CLI's (`gh auth token`, as install_ticino.ps1).</summary>
public sealed class GitHub
{
    public static readonly HttpClient Http = MakeClient();
    string? token;
    bool tokenRead;

    static HttpClient MakeClient()
    {
        var h = new HttpClient(new SocketsHttpHandler
        {
            AutomaticDecompression = DecompressionMethods.None,
            AllowAutoRedirect = true,          // the asset is answered by a redirect to the storage: the token is not
            PooledConnectionLifetime = TimeSpan.FromMinutes(5),   // sent there (.NET drops Authorization on redirects)
            ConnectTimeout = TimeSpan.FromSeconds(30),
        })
        { Timeout = Timeout.InfiniteTimeSpan };
        h.DefaultRequestHeaders.UserAgent.ParseAdd("TicinoServer/1.0 (+https://github.com/wintrymichi/magliasinaNG)");
        return h;
    }

    public string? Token
    {
        get
        {
            if (!tokenRead) { token = ReadToken(); tokenRead = true; }
            return token;
        }
    }

    public bool HasToken => Token != null;

    static string? ReadToken()
    {
        foreach (var name in new[] { "GH_TOKEN", "GITHUB_TOKEN" })
            if (Environment.GetEnvironmentVariable(name) is { Length: > 0 } t) return t.Trim();
        var candidates = new List<string> { "gh" };
        string local = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "GitHubCLI");
        try
        {
            if (Directory.Exists(local))
                candidates.AddRange(Directory.EnumerateFiles(local, "gh.exe", SearchOption.AllDirectories));
        }
        catch { /* not there */ }
        foreach (var exe in candidates)
        {
            try
            {
                var psi = new ProcessStartInfo(exe, "auth token")
                {
                    RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false, CreateNoWindow = true,
                };
                using var p = Process.Start(psi);
                if (p is null) continue;
                string o = p.StandardOutput.ReadToEnd();
                if (!p.WaitForExit(10_000)) { try { p.Kill(); } catch { } continue; }
                if (p.ExitCode == 0 && o.Trim().Length > 0) return o.Trim();
            }
            catch { /* gh not installed there */ }
        }
        return null;
    }

    HttpRequestMessage Request(string url, string accept = "application/vnd.github+json")
    {
        var r = new HttpRequestMessage(HttpMethod.Get, url);
        r.Headers.Accept.ParseAdd(accept);
        if (Token != null && url.StartsWith("https://api.github.com/"))
            r.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Token);
        return r;
    }

    async Task<T?> Get<T>(string path, CancellationToken ct) where T : class
    {
        using var r = await Http.SendAsync(Request("https://api.github.com/" + path), ct);
        if (r.StatusCode == HttpStatusCode.NotFound) return null;
        if (r.StatusCode == HttpStatusCode.Forbidden || (int)r.StatusCode == 429)
            throw new InvalidOperationException("GitHub ha rifiutato la richiesta (limite di richieste raggiunto?): riprova tra qualche minuto.");
        r.EnsureSuccessStatusCode();
        await using var s = await r.Content.ReadAsStreamAsync(ct);
        return await JsonSerializer.DeserializeAsync<T>(s, cancellationToken: ct);
    }

    /// <summary>The release with every asset (paged), or an exception that says why not.</summary>
    public async Task<Release> GetRelease(string repo, string tag, CancellationToken ct)
    {
        var rel = await Get<Release>($"repos/{repo}/releases/tags/{Uri.EscapeDataString(tag)}", ct);
        if (rel is null && HasToken)                 // a draft is not found by tag
        {
            for (int page = 1; page <= 5 && rel is null; page++)
            {
                var list = await Get<List<Release>>($"repos/{repo}/releases?per_page=100&page={page}", ct);
                if (list is null || list.Count == 0) break;
                rel = list.FirstOrDefault(x => x.Tag == tag);
            }
        }
        if (rel is null)
            throw new InvalidOperationException(HasToken
                ? $"La release '{tag}' non esiste in {repo}."
                : $"La release '{tag}' non è stata trovata. Se è una bozza (draft) serve GitHub CLI con 'gh auth login'.");
        for (int page = 1; page <= 20; page++)
        {
            var part = await Get<List<ReleaseAsset>>($"repos/{repo}/releases/{rel.Id}/assets?per_page=100&page={page}", ct)
                       ?? new List<ReleaseAsset>();
            rel.Assets.AddRange(part);
            if (part.Count < 100) break;
        }
        return rel;
    }

    /// <summary>The asset's bytes from offset `from` (resume): drafts through the API with the token, published ones
    /// through the public link.</summary>
    public async Task<HttpResponseMessage> OpenAsset(ReleaseAsset a, long from, CancellationToken ct)
    {
        var req = Token != null ? Request(a.ApiUrl, "application/octet-stream") : Request(a.BrowserUrl, "application/octet-stream");
        if (from > 0) req.Headers.Range = new RangeHeaderValue(from, null);
        var r = await Http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
        if (r.StatusCode == HttpStatusCode.RequestedRangeNotSatisfiable)
        {
            r.Dispose();
            throw new IOException("range");
        }
        r.EnsureSuccessStatusCode();
        return r;
    }
}
