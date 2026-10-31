namespace TicinoServer.Core;

public enum PackKind { Base, Zone, Server }

public enum PackState { Installed, Missing, Update, Unchecked, Queued, Downloading, Verifying, Ready, Error }

/// <summary>One zip of the release and where it stands on this PC.</summary>
public sealed class PackItem : Observable
{
    public PackItem(ReleaseAsset asset, PackKind kind, string zone)
    {
        Asset = asset;
        Kind = kind;
        Zone = zone;
    }

    public ReleaseAsset Asset { get; set; }
    public PackKind Kind { get; }
    public string Zone { get; }
    public string Name => Asset.Name;
    public long Size => Asset.Size;
    public string SizeText => Files.Size(Size);

    public string Title => Kind switch
    {
        PackKind.Base => "Base pack",
        PackKind.Server => "Server program",
        _ => "Zone " + ZoneTitle(Zone) + (Place is null ? "" : " · " + Place),
    };

    string? place;
    /// <summary>The biggest village of the zone, from the spawn points of the base pack (null without one).</summary>
    public string? Place { get => place; set { if (Set(ref place, value)) Raise(nameof(Title)); } }

    PackState state;
    public PackState State
    {
        get => state;
        set
        {
            if (Set(ref state, value))
            {
                Raise(nameof(StateText));
                Raise(nameof(IsBusy));
                Raise(nameof(NeedsDownload));
                Raise(nameof(Glyph));
            }
        }
    }

    double progress;
    /// <summary>0..100 while downloading or checking.</summary>
    public double Progress { get => progress; set => Set(ref progress, value); }

    string detail = "";
    public string Detail { get => detail; set { if (Set(ref detail, value)) Raise(nameof(StateText)); } }

    public bool IsBusy => State is PackState.Downloading or PackState.Verifying;

    public bool NeedsDownload => State is PackState.Missing or PackState.Update or PackState.Error;

    public string StateText => State switch
    {
        PackState.Installed => "Installed",
        PackState.Missing => "To download",
        PackState.Update => "Update available",
        PackState.Unchecked => "To check",
        PackState.Queued => "Queued",
        PackState.Downloading => Detail.Length > 0 ? Detail : "Download…",
        PackState.Verifying => "Checking sha256…",
        PackState.Ready => "Downloaded: installs when the server and the game are stopped",
        PackState.Error => "Error: " + Detail,
        _ => "",
    };

    /// <summary>Segoe Fluent Icons glyph of the state.</summary>
    public string Glyph => State switch
    {
        PackState.Installed => "",   // check mark
        PackState.Missing => "",     // download
        PackState.Update => "",      // sync
        PackState.Unchecked => "",   // diagnostic
        PackState.Queued => "",      // clock
        PackState.Downloading => "",
        PackState.Verifying => "",
        PackState.Ready => "",       // completed
        PackState.Error => "",       // error
        _ => "",
    };

    /// <summary>ti_m1_0 -> "−1, 0" (column and row of the 1,920 m grid, m = minus).</summary>
    static string ZoneTitle(string zone)
    {
        var parts = zone.Replace("ti_", "").Split('_');
        return string.Join(", ", parts.Select(p => p.StartsWith('m') ? "\u2212" + p[1..] : p));
    }
}
