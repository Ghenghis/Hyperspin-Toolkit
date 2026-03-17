using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using HyperSpinToolkit.Models;
using HyperSpinToolkit.Services;
using System.Collections.ObjectModel;
using System.Text.Json.Nodes;

namespace HyperSpinToolkit.ViewModels;

public partial class AuditViewModel : ObservableObject
{
    private readonly McpBridgeService _mcp;

    [ObservableProperty] private bool _isLoading = false;
    [ObservableProperty] private string _statusText = "Ready — run audit to see results";
    [ObservableProperty] private AuditSummary _summary = new();
    [ObservableProperty] private ObservableCollection<SystemAuditRow> _systems = [];
    [ObservableProperty] private ObservableCollection<EmulatorRow> _emulators = [];
    [ObservableProperty] private string _systemFilter = "";
    [ObservableProperty] private string _specificSystem = "";
    [ObservableProperty] private int _auditProgress = 0;

    public AuditViewModel(McpBridgeService mcp) => _mcp = mcp;

    [RelayCommand]
    public async Task RunFullAuditAsync()
    {
        IsLoading = true;
        AuditProgress = 0;
        StatusText = "Running full ecosystem audit (this may take a moment)...";
        Systems.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("audit_full");
            AuditProgress = 90;

            if (result is JsonObject r)
            {
                var sum = r["summary"]?.AsObject();
                if (sum != null)
                {
                    Summary = new AuditSummary
                    {
                        TotalSystems = sum["total_systems"]?.GetValue<int>() ?? 0,
                        SystemsWithRoms = sum["systems_with_roms"]?.GetValue<int>() ?? 0,
                        SystemsWithXml = sum["systems_with_xml"]?.GetValue<int>() ?? 0,
                        TotalRoms = sum["total_roms"]?.GetValue<long>() ?? 0,
                        TotalGamesInXml = sum["total_games_in_xml"]?.GetValue<long>() ?? 0,
                        TotalEmulators = sum["total_emulators"]?.GetValue<int>() ?? 0,
                        HealthyEmulators = sum["healthy_emulators"]?.GetValue<int>() ?? 0,
                        HealthScore = sum["health_score"]?.GetValue<double>() ?? 0,
                    };
                }

                var systemsArr = r["systems"]?.AsArray();
                if (systemsArr != null)
                {
                    foreach (var s in systemsArr)
                    {
                        if (s is not JsonObject sObj) continue;
                        Systems.Add(new SystemAuditRow
                        {
                            Name = sObj["name"]?.GetValue<string>() ?? "",
                            RomCount = sObj["rom_count"]?.GetValue<int>() ?? 0,
                            XmlGameCount = sObj["xml_game_count"]?.GetValue<int>() ?? 0,
                            MatchedGames = sObj["matched_games"]?.GetValue<int>() ?? 0,
                            MissingRoms = sObj["missing_roms"]?.GetValue<int>() ?? 0,
                            ExtraRoms = sObj["extra_roms"]?.GetValue<int>() ?? 0,
                            HealthScore = sObj["health_score"]?.GetValue<double>() ?? 0,
                            IssueCount = sObj["issues"]?.AsArray()?.Count ?? 0,
                        });
                    }
                }
            }

            AuditProgress = 100;
            StatusText = $"Audit complete — {Systems.Count} systems, health {Summary.HealthScoreDisplay}";
        }
        catch (Exception ex)
        {
            StatusText = $"Audit error: {ex.Message}";
        }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task RunSystemAuditAsync()
    {
        if (string.IsNullOrWhiteSpace(SpecificSystem)) { StatusText = "Enter system name first."; return; }
        IsLoading = true;
        StatusText = $"Auditing {SpecificSystem}...";
        try
        {
            var result = await _mcp.CallToolAsync("audit_system", new { system_name = SpecificSystem });
            if (result is JsonObject r)
            {
                Systems.Clear();
                Systems.Add(new SystemAuditRow
                {
                    Name = SpecificSystem,
                    RomCount = r["rom_count"]?.GetValue<int>() ?? 0,
                    XmlGameCount = r["xml_game_count"]?.GetValue<int>() ?? 0,
                    MatchedGames = r["matched_games"]?.GetValue<int>() ?? 0,
                    MissingRoms = r["missing_roms"]?.GetValue<int>() ?? 0,
                    ExtraRoms = r["extra_roms"]?.GetValue<int>() ?? 0,
                    HealthScore = r["health_score"]?.GetValue<double>() ?? 0,
                    IssueCount = r["issues"]?.AsArray()?.Count ?? 0,
                });
                StatusText = $"System audit complete — {SpecificSystem} health {r["health_score"]?.GetValue<double>() ?? 0:F1}%";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task AuditEmulatorsAsync()
    {
        IsLoading = true;
        StatusText = "Auditing emulators...";
        Emulators.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("audit_emulators");
            if (result is JsonArray arr)
            {
                foreach (var e in arr)
                {
                    if (e is not JsonObject obj) continue;
                    Emulators.Add(new EmulatorRow
                    {
                        Name = obj["name"]?.GetValue<string>() ?? "",
                        ExeCount = obj["exe_count"]?.GetValue<int>() ?? 0,
                        FileCount = obj["file_count"]?.GetValue<int>() ?? 0,
                        TotalSizeMb = obj["total_size_mb"]?.GetValue<double>() ?? 0,
                        IsHealthy = obj["is_healthy"]?.GetValue<bool>() ?? false,
                    });
                }
            }
            StatusText = $"Emulator audit complete — {Emulators.Count} emulators";
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }
}
