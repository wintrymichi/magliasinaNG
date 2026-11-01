using System.Text.Json;
using System.Text.Json.Nodes;

namespace TicinoServer.Core;

/// <summary>Picture quality levels of the app; Custom when the sliders were moved by hand.</summary>
public enum Quality { Low, Medium, High, Custom }

/// <summary>The player's settings of the map, settings\ticino.json of the BeamNG user folder (beamng/ticino/README.md,
/// "Settings"). The game reads it when the level starts. Fields the app does not know are kept as they are.
/// Distances are in tiles of 384 m (Chebyshev rings round the car's tile). Object groups can only be drawn nearer
/// than the build's own radius (objects.GROUP_R caps it by path prefix), never farther.</summary>
public sealed class GameSettings
{
    public const double TileM = 384;

    public Quality Quality { get; set; } = Quality.High;
    public int ForestRadius { get; set; } = 4;      // forest.RADIUS (no trees beyond 4: SHARE has 5 entries)
    public int FarRadius { get; set; } = 16;        // level.farRadius (the build's value is the most the server makes)
    public int Buildings { get; set; } = 6;         // objects.GROUP_R.buildings (build: 6)
    public int Roads { get; set; } = 5;             // roads, walls, railway, tunnels, cut slopes (build: 5)
    public int Details { get; set; } = 1;           // street clutter (build caps it at 1)
    // the horizon (stream.lua 570f922, michi 2026-10-31 "voglio vedere di più da lontano"): the base's far ground
    // levels reach the whole of Ticino, LevelInfo.visibleDistance goes to viewKm and the haze thins to fog
    public int ViewKm { get; set; } = 60;           // "viewKm" (0 = the level's 12 km; preset light 25)
    public double Fog { get; set; } = DefaultFog;   // "fog" (0 = the level's 1.3e-4)
    public bool FarLod { get; set; } = true;        // objects.FAR_LOD: the far ground levels
    public const double DefaultFog = 6e-5, LevelFog = 1.3e-4;
    public bool Helper { get; set; } = true;
    public bool Diagnostics { get; set; } = false;
    public int BurstEveryMs { get; set; } = 1000;
    public int BurstMs { get; set; } = 20;
    public int ForestBlock { get; set; } = 3;
    public int ForestHyst { get; set; } = 1;

    public static GameSettings Preset(Quality q) => q switch
    {
        Quality.Low => new GameSettings { Quality = q, ForestRadius = 2, FarRadius = 8, Buildings = 4, Roads = 4, Details = 0, ViewKm = 25 },
        Quality.Medium => new GameSettings { Quality = q, ForestRadius = 3, FarRadius = 10, Buildings = 5, Roads = 5, Details = 1, ViewKm = 40 },
        _ => new GameSettings { Quality = Quality.High },
    };

    /// <summary>The quality level these distances belong to (Custom when none).</summary>
    public Quality Match()
    {
        foreach (var q in new[] { Quality.Low, Quality.Medium, Quality.High })
        {
            var p = Preset(q);
            if (p.ForestRadius == ForestRadius && p.FarRadius == FarRadius && p.Buildings == Buildings &&
                p.Roads == Roads && p.Details == Details && p.ViewKm == ViewKm)
                return q;
        }
        return Quality.Custom;
    }

    public GameSettings Clone() => (GameSettings)MemberwiseClone();

    /// <summary>The GROUP_R table the mod gets (objects.lua: the longest prefix of a group's path wins).</summary>
    public Dictionary<string, int> GroupCaps()
    {
        int d = Details;
        return new Dictionary<string, int>
        {
            ["props/street_life"] = d,
            ["props/delineators"] = d,
            ["props/shopfronts"] = d,
            ["props/osm/furniture"] = d,
            ["props"] = d + 1,
            ["roads/markings"] = Math.Min(d + 1, Roads),
            ["roads"] = Roads,
            ["walls"] = Roads,
            ["railway"] = Roads,
            ["tunnels"] = Roads,
            ["level_objects/terrain_skin"] = Roads,
            ["buildings/details"] = Math.Min(d + 2, Buildings),
            ["buildings/extras"] = Math.Min(d + 2, Buildings),
            ["buildings"] = Buildings,
        };
    }

    static JsonObject Obj(JsonObject root, string name)
    {
        if (root[name] is JsonObject o) return o;
        o = new JsonObject();
        root[name] = o;
        return o;
    }

    static int Int(JsonNode? n, int fallback, int min, int max)
    {
        try
        {
            if (n is JsonValue v && v.TryGetValue(out double x)) return Math.Clamp((int)Math.Round(x), min, max);
        }
        catch { /* not a number */ }
        return fallback;
    }

    static string? Str(JsonNode? n) => n is JsonValue v && v.TryGetValue(out string? t) ? t : null;

    static double? Num(JsonNode? n)
    {
        try { return n is JsonValue v && v.TryGetValue(out double x) ? x : null; }
        catch { return null; }
    }

    /// <summary>The share of the scene the haze hides at 10 km (exponential fog: 6e-5 hides 45 %).</summary>
    public static double HiddenAt10Km(double fog) => 1 - Math.Exp(-fog * 10_000);

    static JsonObject ReadRoot(string path)
    {
        try
        {
            if (File.Exists(path) && JsonNode.Parse(File.ReadAllText(path)) is JsonObject o) return o;
        }
        catch (Exception e)
        {
            Log.Write($"{path} is not valid JSON ({e.Message}): written again");
        }
        return new JsonObject();
    }

    public static GameSettings Load(string path)
    {
        var root = ReadRoot(path);
        string preset = Str(root["preset"]) ?? "standard";
        // what the mod itself runs with for a key the file does not have ("light" leaves GROUP_R at the build's)
        var s = ModDefaults(preset == "light");
        var forest = root["forest"] as JsonObject;
        var stream = root["stream"] as JsonObject;
        var level = root["level"] as JsonObject;
        var caps = (root["objects"] as JsonObject)?["GROUP_R"] as JsonObject;
        s.ForestRadius = Int(forest?["RADIUS"], s.ForestRadius, 1, 4);
        s.ForestBlock = Int(forest?["BLOCK"], s.ForestBlock, 1, 4);
        s.ForestHyst = Int(forest?["HYST"], s.ForestHyst, 0, 2);
        s.FarRadius = Int(level?["farRadius"], s.FarRadius, 4, 16);
        s.BurstEveryMs = Int(stream?["BURST_EVERY_MS"], s.BurstEveryMs, 200, 3000);
        s.BurstMs = Int(stream?["BURST_MS"], s.BurstMs, 5, 60);
        s.Buildings = Int(caps?["buildings"], s.Buildings, 2, 6);
        s.Roads = Int(caps?["roads"], s.Roads, 2, 5);
        s.Details = Int(caps?["props/street_life"], s.Details, 0, 2);
        if (Num(root["viewKm"]) is { } vk && vk >= 0) s.ViewKm = Math.Clamp(vk == 0 ? 12 : (int)Math.Round(vk), 12, 80);
        if (Num(root["fog"]) is { } fg && fg >= 0) s.Fog = Math.Clamp(fg == 0 ? LevelFog : fg, 1e-5, 2e-4);
        if ((root["objects"] as JsonObject)?["FAR_LOD"] is JsonValue fl && fl.TryGetValue(out bool flb)) s.FarLod = flb;
        if (root["helper"] is JsonValue h && h.TryGetValue(out bool hb)) s.Helper = hb;
        if (root["diagnostics"] is JsonValue g && g.TryGetValue(out bool gb)) s.Diagnostics = gb;
        string? q = Str((root["app"] as JsonObject)?["quality"]);
        s.Quality = Enum.TryParse<Quality>(q, true, out var qq) ? qq : s.Match();
        if (s.Quality != Quality.Custom && s.Match() != s.Quality) s.Quality = Quality.Custom;
        return s;
    }

    /// <summary>What the mod does with no key in the file (stream.lua: the built level, PRESETS.light over it).</summary>
    static GameSettings ModDefaults(bool light) => new()
    {
        ForestRadius = light ? 3 : 4, FarRadius = light ? 10 : 16, Buildings = 6, Roads = 5, Details = 1,
        ViewKm = light ? 25 : 60, Fog = DefaultFog, FarLod = true,
        Helper = true, Diagnostics = false, BurstEveryMs = 1000, BurstMs = 20, ForestBlock = 3, ForestHyst = 1,
    };

    /// <summary>Writes only what differs from the mod's own values (the key goes when it is back at the mod's value),
    /// so a later mod with new defaults is not held back by a file the app wrote; keys the app does not know stay.</summary>
    public void Save(string path)
    {
        var root = ReadRoot(path);
        // "light" also thins the far trees (forest.SHARE, which JSON cannot set: a Lua table from 0)
        bool light = Quality is Quality.Low or Quality.Medium;
        var d = ModDefaults(light);
        Set(root, null, "preset", light ? "light" : null);
        Set(root, null, "helper", Helper == d.Helper ? null : Helper);
        Set(root, null, "diagnostics", Diagnostics == d.Diagnostics ? null : Diagnostics);
        Set(root, "forest", "RADIUS", ForestRadius == d.ForestRadius ? null : ForestRadius);
        Set(root, "forest", "BLOCK", ForestBlock == d.ForestBlock ? null : ForestBlock);
        Set(root, "forest", "HYST", ForestHyst == d.ForestHyst ? null : ForestHyst);
        Set(root, "level", "farRadius", FarRadius == d.FarRadius ? null : FarRadius);
        Set(root, "stream", "BURST_EVERY_MS", BurstEveryMs == d.BurstEveryMs ? null : BurstEveryMs);
        Set(root, "stream", "BURST_MS", BurstMs == d.BurstMs ? null : BurstMs);
        Set(root, null, "viewKm", ViewKm == d.ViewKm ? null : ViewKm);
        Set(root, null, "fog", Math.Abs(Fog - d.Fog) < 1e-7 ? null : Math.Round(Fog, 7));
        Set(root, "objects", "FAR_LOD", FarLod == d.FarLod ? null : FarLod);
        // the mod takes GROUP_R as a whole table (applyFields replaces it): all of it, or none
        JsonObject? caps = null;
        if (Buildings != d.Buildings || Roads != d.Roads || Details != d.Details)
        {
            caps = new JsonObject();
            foreach (var (k, v) in GroupCaps()) caps[k] = v;
        }
        Set(root, "objects", "GROUP_R", caps);
        Set(root, "app", "quality", Quality == Quality.High ? null : Quality.ToString().ToLowerInvariant());
        Files.WriteAtomic(path, root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    /// <summary>root[section][key] = value; null removes the key, and the section when it is left empty.</summary>
    static void Set(JsonObject root, string? section, string key, JsonNode? value)
    {
        JsonObject? o = section is null ? root : root[section] as JsonObject;
        if (value is null)
        {
            o?.Remove(key);
            if (section != null && o is { Count: 0 }) root.Remove(section);
            return;
        }
        if (o is null) o = Obj(root, section!);
        o[key] = value;
    }
}
