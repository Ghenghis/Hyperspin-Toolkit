using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using HyperSpinToolkit.Models;
using HyperSpinToolkit.Services;
using System.Collections.ObjectModel;
using System.Text.Json.Nodes;

namespace HyperSpinToolkit.ViewModels;

public partial class DrivesViewModel : ObservableObject
{
    private readonly McpBridgeService _mcp;

    [ObservableProperty] private bool _isLoading = false;
    [ObservableProperty] private string _statusText = "Ready — scan drives to begin";
    [ObservableProperty] private ObservableCollection<DriveModel> _drives = [];
    [ObservableProperty] private ObservableCollection<DriveRoleStatus> _roleStatuses = [];
    [ObservableProperty] private DriveModel? _selectedDrive;

    // Assign role
    [ObservableProperty] private string _assignLetter = "";
    [ObservableProperty] private string _assignRole = "primary";
    [ObservableProperty] private string _assignResult = "";

    // Health check
    [ObservableProperty] private string _healthLetter = "";
    [ObservableProperty] private DriveHealthModel? _healthResult;

    // Compare/Sync
    [ObservableProperty] private string _compareSource = "";
    [ObservableProperty] private string _compareDest = "";
    [ObservableProperty] private string _compareResult = "";

    // Migrate
    [ObservableProperty] private string _migrateSource = "";
    [ObservableProperty] private string _migrateDest = "";
    [ObservableProperty] private bool _migrateVerify = false;
    [ObservableProperty] private string _migrateResult = "";
    [ObservableProperty] private bool _isMigrating = false;
    [ObservableProperty] private int _migrateProgress = 0;

    public string[] RoleChoices => ["primary", "secondary", "tertiary"];

    public DrivesViewModel(McpBridgeService mcp) => _mcp = mcp;

    [RelayCommand]
    public async Task ScanDrivesAsync()
    {
        IsLoading = true;
        StatusText = "Scanning connected drives...";
        try
        {
            var result = await _mcp.CallToolAsync("drives_scan");
            Drives.Clear();
            if (result is JsonArray arr)
            {
                foreach (var d in arr)
                {
                    if (d is not JsonObject obj) continue;
                    Drives.Add(new DriveModel
                    {
                        Letter = obj["letter"]?.GetValue<string>() ?? "",
                        Label = obj["label"]?.GetValue<string>() ?? "",
                        TotalHuman = obj["total_human"]?.GetValue<string>() ?? "",
                        UsedHuman = obj["used_human"]?.GetValue<string>() ?? "",
                        FreeHuman = obj["free_human"]?.GetValue<string>() ?? "",
                        IsArcade = obj["is_arcade"]?.GetValue<bool>() ?? false,
                        IsSystem = obj["is_system"]?.GetValue<bool>() ?? false,
                        ArcadeRoot = obj["arcade_root"]?.GetValue<string>() ?? "",
                    });
                }
            }
            await LoadStatusAsync();
            StatusText = $"Found {Drives.Count} drives";
        }
        catch (Exception ex) { StatusText = $"Scan error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task LoadStatusAsync()
    {
        var result = await _mcp.CallToolAsync("drives_status");
        RoleStatuses.Clear();
        if (result is JsonObject driveObj)
        {
            var drives = driveObj["drives"]?.AsObject();
            if (drives == null) return;
            foreach (var (role, info) in drives)
            {
                if (info is not JsonObject infoObj) continue;
                var assigned = infoObj["assigned"]?.GetValue<bool>() ?? false;
                RoleStatuses.Add(new DriveRoleStatus
                {
                    Role = role,
                    Letter = infoObj["letter"]?.GetValue<string>() ?? "",
                    Path = assigned ? infoObj["path"]?.GetValue<string>() ?? "" : "not assigned",
                    Label = infoObj["label"]?.GetValue<string>() ?? "",
                    TotalHuman = infoObj["total_human"]?.GetValue<string>() ?? "",
                    FreeHuman = infoObj["free_human"]?.GetValue<string>() ?? "",
                    UsedPct = $"{infoObj["used_pct"]?.GetValue<double>() ?? 0:F0}%",
                    IsOk = (infoObj["connected"]?.GetValue<bool>() ?? false) && (infoObj["root_exists"]?.GetValue<bool>() ?? false),
                    IsAssigned = assigned,
                });
            }
        }
    }

    [RelayCommand]
    public async Task AssignRoleAsync()
    {
        if (string.IsNullOrWhiteSpace(AssignLetter)) { AssignResult = "Enter a drive letter first."; return; }
        IsLoading = true;
        AssignResult = $"Assigning {AssignRole} → {AssignLetter.ToUpper()}:...";
        try
        {
            var result = await _mcp.CallToolAsync("drives_set", new { role = AssignRole, letter = AssignLetter.Trim().ToUpper() });
            AssignResult = result?["message"]?.GetValue<string>() ?? $"✓ {AssignRole} → {AssignLetter.ToUpper()}:\\";
            await LoadStatusAsync();
            StatusText = AssignResult;
        }
        catch (Exception ex) { AssignResult = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task CheckHealthAsync()
    {
        if (string.IsNullOrWhiteSpace(HealthLetter)) { StatusText = "Enter drive letter for health check."; return; }
        IsLoading = true;
        StatusText = $"Checking health of {HealthLetter.ToUpper()}:...";
        try
        {
            var result = await _mcp.CallToolAsync("drives_health", new { letter = HealthLetter.Trim().ToUpper() });
            if (result is JsonObject h)
            {
                var smart = h["smart"]?.AsObject();
                var wmic = h["wmic"]?.AsObject();
                HealthResult = new DriveHealthModel
                {
                    Letter = HealthLetter.ToUpper(),
                    TotalGb = h["total_gb"]?.ToString() ?? "",
                    FreeGb = h["free_gb"]?.ToString() ?? "",
                    UsedPct = $"{h["used_pct"]?.ToString() ?? "?"}%",
                    SmartHealth = smart?["health"]?.GetValue<string>() ?? "UNKNOWN",
                    TemperatureC = smart?["temperature_c"]?.ToString() ?? "",
                    ReallocatedSectors = smart?["reallocated_sectors"]?.ToString() ?? "",
                    PowerOnHours = smart?["power_on_hours"]?.ToString() ?? "",
                    Device = wmic?["caption"]?.GetValue<string>() ?? "",
                    Interface = wmic?["interface"]?.GetValue<string>() ?? "",
                };
            }
            StatusText = $"Health check complete for {HealthLetter.ToUpper()}:";
        }
        catch (Exception ex) { StatusText = $"Health check error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task CompareAsync()
    {
        if (string.IsNullOrWhiteSpace(CompareSource) || string.IsNullOrWhiteSpace(CompareDest))
        { CompareResult = "Enter both source and destination paths."; return; }

        IsLoading = true;
        CompareResult = "Comparing directories...";
        try
        {
            var result = await _mcp.CallToolAsync("drives_compare", new { source_root = CompareSource, dest_root = CompareDest });
            if (result is JsonObject r)
            {
                CompareResult =
                    $"Missing on dest:     {r["missing_count"]?.GetValue<int>() ?? 0:N0} files\n" +
                    $"Extra on dest:       {r["extra_count"]?.GetValue<int>() ?? 0:N0} files\n" +
                    $"Size mismatches:     {r["size_mismatch_count"]?.GetValue<int>() ?? 0:N0} files\n" +
                    $"In sync:             {r["in_sync_count"]?.GetValue<int>() ?? 0:N0} files";
            }
        }
        catch (Exception ex) { CompareResult = $"Compare error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task MigrateDryRunAsync()
    {
        await RunMigrateAsync(dryRun: true);
    }

    [RelayCommand]
    public async Task MigrateAsync()
    {
        await RunMigrateAsync(dryRun: false);
    }

    private async Task RunMigrateAsync(bool dryRun)
    {
        if (string.IsNullOrWhiteSpace(MigrateSource) || string.IsNullOrWhiteSpace(MigrateDest))
        { MigrateResult = "Enter source and destination directories."; return; }

        IsMigrating = true;
        MigrateProgress = 0;
        MigrateResult = dryRun ? "Calculating (dry-run)..." : "Starting migration...";
        try
        {
            var result = await _mcp.CallToolAsync("drives_migrate", new
            {
                source_root = MigrateSource,
                dest_root = MigrateDest,
                verify = MigrateVerify,
                dry_run = dryRun,
            });
            if (result is JsonObject r)
            {
                MigrateProgress = 100;
                MigrateResult =
                    $"Copied:   {r["copied"]?.GetValue<int>() ?? 0:N0} files  ({r["bytes_human"]?.GetValue<string>() ?? "?"})\n" +
                    $"Skipped:  {r["skipped"]?.GetValue<int>() ?? 0:N0} already done\n" +
                    $"Failed:   {r["failed"]?.GetValue<int>() ?? 0:N0}\n" +
                    $"Time:     {r["elapsed_human"]?.GetValue<string>() ?? "?"}";
                if (dryRun) MigrateResult = "[DRY RUN]\n" + MigrateResult;
            }
        }
        catch (Exception ex) { MigrateResult = $"Error: {ex.Message}"; }
        finally { IsMigrating = false; }
    }
}
