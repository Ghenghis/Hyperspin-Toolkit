namespace HyperSpinToolkit.Models;

public class AuditSummary
{
    public int TotalSystems { get; set; }
    public int SystemsWithRoms { get; set; }
    public int SystemsWithXml { get; set; }
    public long TotalRoms { get; set; }
    public long TotalGamesInXml { get; set; }
    public int TotalEmulators { get; set; }
    public int HealthyEmulators { get; set; }
    public double HealthScore { get; set; }
    public string HealthScoreDisplay => $"{HealthScore:F1}%";
    public string HealthColor => HealthScore >= 80 ? "#22c55e" : HealthScore >= 50 ? "#f59e0b" : "#ef4444";
}

public class SystemAuditRow
{
    public string Name { get; set; } = "";
    public int RomCount { get; set; }
    public int XmlGameCount { get; set; }
    public int MatchedGames { get; set; }
    public int MissingRoms { get; set; }
    public int ExtraRoms { get; set; }
    public double HealthScore { get; set; }
    public string HealthDisplay => $"{HealthScore:F0}%";
    public string HealthColor => HealthScore >= 80 ? "#22c55e" : HealthScore >= 50 ? "#f59e0b" : "#ef4444";
    public int IssueCount { get; set; }
}

public class EmulatorRow
{
    public string Name { get; set; } = "";
    public int ExeCount { get; set; }
    public int FileCount { get; set; }
    public double TotalSizeMb { get; set; }
    public bool IsHealthy { get; set; }
    public string HealthDisplay => IsHealthy ? "✓" : "✗";
    public string HealthColor => IsHealthy ? "#22c55e" : "#ef4444";
}

public class BackupRow
{
    public int Id { get; set; }
    public string BackupType { get; set; } = "";
    public string Target { get; set; } = "";
    public int FileCount { get; set; }
    public string SizeMb { get; set; } = "";
    public string Status { get; set; } = "";
    public string CreatedAt { get; set; } = "";
}
