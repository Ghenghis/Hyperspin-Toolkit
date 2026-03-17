using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using HyperSpinToolkit.Models;
using HyperSpinToolkit.Services;
using System.Collections.ObjectModel;
using System.Text.Json.Nodes;

namespace HyperSpinToolkit.ViewModels;

public partial class DashboardViewModel : ObservableObject
{
    private readonly McpBridgeService _mcp;

    [ObservableProperty] private bool _isLoading = false;
    [ObservableProperty] private string _statusText = "Ready";
    [ObservableProperty] private AuditSummary _summary = new();
    [ObservableProperty] private ObservableCollection<DriveRoleStatus> _driveStatuses = [];
    [ObservableProperty] private string _bridgeStatus = "Connecting...";
    [ObservableProperty] private string _bridgeColor = "#f59e0b";
    [ObservableProperty] private int _totalSystems = 0;
    [ObservableProperty] private long _totalRoms = 0;
    [ObservableProperty] private int _totalEmulators = 0;
    [ObservableProperty] private string _healthScore = "—";
    [ObservableProperty] private string _healthColor = "#6b7280";
    [ObservableProperty] private string _primaryDrive = "Not assigned";
    [ObservableProperty] private string _secondaryDrive = "Not assigned";
    [ObservableProperty] private string _lastRefreshed = "Never";

    public DashboardViewModel(McpBridgeService mcp)
    {
        _mcp = mcp;
        UpdateBridgeStatus();
    }

    private void UpdateBridgeStatus()
    {
        if (_mcp.IsConnected)
        {
            BridgeStatus = "Connected";
            BridgeColor = "#22c55e";
        }
        else
        {
            BridgeStatus = $"Offline — {_mcp.LastError ?? "not started"}";
            BridgeColor = "#ef4444";
        }
    }

    [RelayCommand]
    public async Task RefreshAsync()
    {
        IsLoading = true;
        StatusText = "Loading dashboard...";
        UpdateBridgeStatus();

        try
        {
            // Load drive status
            var driveResult = await _mcp.CallToolAsync("drives_status");
            if (driveResult is JsonObject driveObj)
            {
                var drives = driveObj["drives"]?.AsObject();
                if (drives != null)
                {
                    DriveStatuses.Clear();
                    foreach (var (role, info) in drives)
                    {
                        if (info is not JsonObject infoObj) continue;
                        var assigned = infoObj["assigned"]?.GetValue<bool>() ?? false;
                        var letter = infoObj["letter"]?.GetValue<string>() ?? "";

                        DriveStatuses.Add(new DriveRoleStatus
                        {
                            Role = role,
                            Letter = letter,
                            Path = infoObj["path"]?.GetValue<string>() ?? "not assigned",
                            Label = infoObj["label"]?.GetValue<string>() ?? "",
                            TotalHuman = infoObj["total_human"]?.GetValue<string>() ?? "",
                            FreeHuman = infoObj["free_human"]?.GetValue<string>() ?? "",
                            UsedPct = $"{infoObj["used_pct"]?.GetValue<double>() ?? 0:F0}%",
                            IsOk = (infoObj["connected"]?.GetValue<bool>() ?? false) && (infoObj["root_exists"]?.GetValue<bool>() ?? false),
                            IsAssigned = assigned,
                        });

                        if (role == "primary") PrimaryDrive = assigned ? $"{letter}:\\" : "Not assigned";
                        if (role == "secondary") SecondaryDrive = assigned ? $"{letter}:\\" : "Not assigned";
                    }
                }
            }

            // Load quick stats from get_stats tool
            var statsResult = await _mcp.CallToolAsync("get_stats");
            if (statsResult is JsonObject statsObj)
            {
                TotalSystems = statsObj["total_systems"]?.GetValue<int>() ?? 0;
                TotalRoms = statsObj["total_roms"]?.GetValue<long>() ?? 0;
                TotalEmulators = statsObj["total_emulators"]?.GetValue<int>() ?? 0;
                var hs = statsObj["health_score"]?.GetValue<double>() ?? 0;
                HealthScore = $"{hs:F1}%";
                HealthColor = hs >= 80 ? "#22c55e" : hs >= 50 ? "#f59e0b" : "#ef4444";
            }

            LastRefreshed = DateTime.Now.ToString("HH:mm:ss");
            StatusText = "Dashboard refreshed";
        }
        catch (Exception ex)
        {
            StatusText = $"Error: {ex.Message}";
        }
        finally
        {
            IsLoading = false;
        }
    }
}
