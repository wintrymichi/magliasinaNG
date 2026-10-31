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
        PackKind.Base => "Pacchetto base",
        PackKind.Server => "Programma del server",
        _ => "Zona " + Zone.Replace("ti_", "").Replace('_', '.'),
    };

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
        PackState.Installed => "Installato",
        PackState.Missing => "Da scaricare",
        PackState.Update => "Aggiornamento disponibile",
        PackState.Unchecked => "Da verificare",
        PackState.Queued => "In coda",
        PackState.Downloading => Detail.Length > 0 ? Detail : "Download…",
        PackState.Verifying => "Verifica sha256…",
        PackState.Ready => "Scaricato: si installa a server e gioco fermi",
        PackState.Error => "Errore: " + Detail,
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
}
