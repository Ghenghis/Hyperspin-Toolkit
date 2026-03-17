namespace HyperSpinToolkit.Models;

public class DriveModel
{
    public string Letter { get; set; } = "";
    public string Label { get; set; } = "";
    public string TotalHuman { get; set; } = "";
    public string UsedHuman { get; set; } = "";
    public string FreeHuman { get; set; } = "";
    public bool IsArcade { get; set; }
    public bool IsSystem { get; set; }
    public string ArcadeRoot { get; set; } = "";
    public string Role { get; set; } = "";
    public string DisplayLetter => $"{Letter}:";
    public string ArcadeStatus => IsSystem ? "System" : IsArcade ? "YES" : "no";
}

public class DriveHealthModel
{
    public string Letter { get; set; } = "";
    public string TotalGb { get; set; } = "";
    public string FreeGb { get; set; } = "";
    public string UsedPct { get; set; } = "";
    public string SmartHealth { get; set; } = "UNKNOWN";
    public string TemperatureC { get; set; } = "";
    public string ReallocatedSectors { get; set; } = "";
    public string PowerOnHours { get; set; } = "";
    public string Device { get; set; } = "";
    public string Interface { get; set; } = "";
    public string StatusColor => SmartHealth == "PASSED" ? "#22c55e" : SmartHealth == "FAILED" ? "#ef4444" : "#f59e0b";
}

public class DriveRoleStatus
{
    public string Role { get; set; } = "";
    public string Letter { get; set; } = "";
    public string Path { get; set; } = "";
    public string Label { get; set; } = "";
    public string TotalHuman { get; set; } = "";
    public string FreeHuman { get; set; } = "";
    public string UsedPct { get; set; } = "";
    public bool IsOk { get; set; }
    public bool IsAssigned { get; set; }
}
