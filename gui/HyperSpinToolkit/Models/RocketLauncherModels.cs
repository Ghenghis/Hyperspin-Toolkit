namespace HyperSpinToolkit.Models;

// ── M59 — Media Manager Models ──────────────────────────────────────

public class RlMediaCoverageRow
{
    public string System { get; set; } = "";
    public int FadeCount { get; set; }
    public int BezelCount { get; set; }
    public int PauseCount { get; set; }
    public double CoveragePct { get; set; }
    public string CoverageDisplay => $"{CoveragePct:F0}%";
    public string CoverageColor => CoveragePct >= 80 ? "#22c55e" : CoveragePct >= 50 ? "#f59e0b" : "#ef4444";
    public int IssueCount { get; set; }
}

public class RlFadeRow
{
    public string Game { get; set; } = "";
    public int Layer { get; set; }
    public string FileName { get; set; } = "";
    public string Dimensions { get; set; } = "";
    public string Status { get; set; } = "OK";
    public string StatusColor => Status == "OK" ? "#22c55e" : "#ef4444";
}

public class RlBezelRow
{
    public string Game { get; set; } = "";
    public string FileName { get; set; } = "";
    public string Dimensions { get; set; } = "";
    public string Orientation { get; set; } = "";
    public bool HasBackground { get; set; }
    public string BgDisplay => HasBackground ? "YES" : "—";
    public string Status { get; set; } = "OK";
    public string StatusColor => Status == "OK" ? "#22c55e" : "#ef4444";
}

public class RlPauseRow
{
    public string Game { get; set; } = "";
    public string Category { get; set; } = "";
    public string FileName { get; set; } = "";
    public string FileType { get; set; } = "";
}

public class RlMissingMediaRow
{
    public string Game { get; set; } = "";
    public bool MissingFade { get; set; }
    public bool MissingBezel { get; set; }
    public bool MissingPause { get; set; }
    public string FadeDisplay => MissingFade ? "MISSING" : "OK";
    public string BezelDisplay => MissingBezel ? "MISSING" : "OK";
    public string PauseDisplay => MissingPause ? "MISSING" : "OK";
    public string FadeColor => MissingFade ? "#ef4444" : "#22c55e";
    public string BezelColor => MissingBezel ? "#ef4444" : "#22c55e";
    public string PauseColor => MissingPause ? "#ef4444" : "#22c55e";
}

public class RlIssueRow
{
    public string Severity { get; set; } = "info";
    public string Message { get; set; } = "";
    public string Source { get; set; } = "";
    public string SeverityColor => Severity switch
    {
        "error" => "#ef4444",
        "warn" => "#f59e0b",
        _ => "#6366f1"
    };
}

// ── M60 — Stats / Keymapper / 7z Models ────────────────────────────

public class RlGameStatsRow
{
    public string Game { get; set; } = "";
    public string System { get; set; } = "";
    public int PlayCount { get; set; }
    public string TotalTime { get; set; } = "";
    public string LastPlayed { get; set; } = "";
    public string AvgSession { get; set; } = "";
}

public class RlKeymapperRow
{
    public string ProfileName { get; set; } = "";
    public string KeymapperType { get; set; } = "";
    public string System { get; set; } = "";
    public int MappingCount { get; set; }
    public string Status { get; set; } = "OK";
    public string StatusColor => Status == "OK" ? "#22c55e" : "#f59e0b";
}

public class RlMultiGameRow
{
    public string Game { get; set; } = "";
    public int DiscCount { get; set; }
    public string Status { get; set; } = "OK";
    public string StatusColor => Status == "OK" ? "#22c55e" : "#ef4444";
}

public class Rl7zSettingsModel
{
    public string ExtractPath { get; set; } = "";
    public string TempDir { get; set; } = "";
    public bool ExtractPathExists { get; set; }
    public bool TempDirExists { get; set; }
    public string CacheSize { get; set; } = "";
    public string CleanupPolicy { get; set; } = "";
    public int IssueCount { get; set; }
}
