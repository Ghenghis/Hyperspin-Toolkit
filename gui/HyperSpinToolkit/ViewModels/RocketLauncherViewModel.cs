using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using HyperSpinToolkit.Models;
using HyperSpinToolkit.Services;
using System.Collections.ObjectModel;
using System.Text.Json.Nodes;

namespace HyperSpinToolkit.ViewModels;

public partial class RocketLauncherViewModel : ObservableObject
{
    private readonly McpBridgeService _mcp;

    // ── Shared state ────────────────────────────────────────────────
    [ObservableProperty] private bool _isLoading;
    [ObservableProperty] private string _statusText = "Ready — select a tab to begin";
    [ObservableProperty] private string _selectedSystem = "";
    [ObservableProperty] private int _selectedTabIndex;

    // ── M59 — Media coverage ────────────────────────────────────────
    [ObservableProperty] private ObservableCollection<RlMediaCoverageRow> _mediaCoverage = [];
    [ObservableProperty] private int _totalFade;
    [ObservableProperty] private int _totalBezels;
    [ObservableProperty] private int _totalPause;
    [ObservableProperty] private double _overallCoverage;

    // ── M59 — System detail (fade / bezel / pause) ─────────────────
    [ObservableProperty] private ObservableCollection<RlFadeRow> _fadeItems = [];
    [ObservableProperty] private ObservableCollection<RlBezelRow> _bezelItems = [];
    [ObservableProperty] private ObservableCollection<RlPauseRow> _pauseItems = [];
    [ObservableProperty] private ObservableCollection<RlMissingMediaRow> _missingMedia = [];
    [ObservableProperty] private ObservableCollection<RlIssueRow> _mediaIssues = [];

    // ── M60 — Stats ─────────────────────────────────────────────────
    [ObservableProperty] private ObservableCollection<RlGameStatsRow> _gameStats = [];
    [ObservableProperty] private ObservableCollection<RlGameStatsRow> _mostPlayed = [];
    [ObservableProperty] private int _totalPlays;
    [ObservableProperty] private string _totalPlayTime = "";

    // ── M60 — Keymapper ─────────────────────────────────────────────
    [ObservableProperty] private ObservableCollection<RlKeymapperRow> _keymappers = [];
    [ObservableProperty] private int _totalProfiles;

    // ── M60 — MultiGame ─────────────────────────────────────────────
    [ObservableProperty] private ObservableCollection<RlMultiGameRow> _multiGames = [];

    // ── M60 — 7z ────────────────────────────────────────────────────
    [ObservableProperty] private Rl7zSettingsModel _sevenZipSettings = new();
    [ObservableProperty] private ObservableCollection<RlIssueRow> _sevenZipIssues = [];

    public RocketLauncherViewModel(McpBridgeService mcp) => _mcp = mcp;

    // ═════════════════════════════════════════════════════════════════
    // M59 — Media Coverage (all systems)
    // ═════════════════════════════════════════════════════════════════

    [RelayCommand]
    public async Task LoadMediaCoverageAsync()
    {
        IsLoading = true;
        StatusText = "Scanning RL media coverage across all systems...";
        MediaCoverage.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("rl_media_coverage");
            if (result is JsonObject r)
            {
                TotalFade = r["totals"]?["fade"]?.GetValue<int>() ?? 0;
                TotalBezels = r["totals"]?["bezels"]?.GetValue<int>() ?? 0;
                TotalPause = r["totals"]?["pause"]?.GetValue<int>() ?? 0;
                OverallCoverage = r["overall_coverage_pct"]?.GetValue<double>() ?? 0;

                var systems = r["systems"]?.AsArray();
                if (systems != null)
                {
                    foreach (var s in systems)
                    {
                        if (s is not JsonObject obj) continue;
                        MediaCoverage.Add(new RlMediaCoverageRow
                        {
                            System = obj["system"]?.GetValue<string>() ?? "",
                            FadeCount = obj["fade_count"]?.GetValue<int>() ?? 0,
                            BezelCount = obj["bezel_count"]?.GetValue<int>() ?? 0,
                            PauseCount = obj["pause_count"]?.GetValue<int>() ?? 0,
                            CoveragePct = obj["coverage_pct"]?.GetValue<double>() ?? 0,
                            IssueCount = obj["issue_count"]?.GetValue<int>() ?? 0,
                        });
                    }
                }
                StatusText = $"Media coverage: {MediaCoverage.Count} systems, {OverallCoverage:F0}% overall";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    // ═════════════════════════════════════════════════════════════════
    // M59 — System Media Detail (fade, bezel, pause for one system)
    // ═════════════════════════════════════════════════════════════════

    [RelayCommand]
    public async Task LoadSystemMediaAsync()
    {
        if (string.IsNullOrWhiteSpace(SelectedSystem)) { StatusText = "Enter a system name first."; return; }
        IsLoading = true;
        StatusText = $"Loading media detail for {SelectedSystem}...";
        FadeItems.Clear(); BezelItems.Clear(); PauseItems.Clear(); MediaIssues.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("rl_media_system", new { system = SelectedSystem });
            if (result is JsonObject r)
            {
                ParseFade(r["fade"]?.AsObject());
                ParseBezels(r["bezels"]?.AsObject());
                ParsePause(r["pause"]?.AsObject());
                ParseIssues(r["issues"]?.AsArray(), MediaIssues);
                StatusText = $"{SelectedSystem}: {FadeItems.Count} fades, {BezelItems.Count} bezels, {PauseItems.Count} pause assets";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task LoadMissingMediaAsync()
    {
        if (string.IsNullOrWhiteSpace(SelectedSystem)) { StatusText = "Enter a system name first."; return; }
        IsLoading = true;
        StatusText = $"Finding missing media for {SelectedSystem}...";
        MissingMedia.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("rl_media_missing", new { system = SelectedSystem });
            if (result is JsonObject r)
            {
                var missing = r["missing"]?.AsArray();
                if (missing != null)
                {
                    foreach (var m in missing)
                    {
                        if (m is not JsonObject obj) continue;
                        MissingMedia.Add(new RlMissingMediaRow
                        {
                            Game = obj["game"]?.GetValue<string>() ?? "",
                            MissingFade = obj["missing_fade"]?.GetValue<bool>() ?? false,
                            MissingBezel = obj["missing_bezel"]?.GetValue<bool>() ?? false,
                            MissingPause = obj["missing_pause"]?.GetValue<bool>() ?? false,
                        });
                    }
                }
                StatusText = $"Missing media: {MissingMedia.Count} games with gaps in {SelectedSystem}";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    // ═════════════════════════════════════════════════════════════════
    // M60 — Play Statistics
    // ═════════════════════════════════════════════════════════════════

    [RelayCommand]
    public async Task LoadSystemStatsAsync()
    {
        if (string.IsNullOrWhiteSpace(SelectedSystem)) { StatusText = "Enter a system name first."; return; }
        IsLoading = true;
        StatusText = $"Loading play stats for {SelectedSystem}...";
        GameStats.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("rl_stats_system", new { system = SelectedSystem });
            if (result is JsonObject r)
            {
                TotalPlays = r["total_plays"]?.GetValue<int>() ?? 0;
                TotalPlayTime = r["total_time_display"]?.GetValue<string>() ?? "";
                var games = r["games"]?.AsArray();
                if (games != null)
                {
                    foreach (var g in games)
                    {
                        if (g is not JsonObject obj) continue;
                        GameStats.Add(new RlGameStatsRow
                        {
                            Game = obj["game"]?.GetValue<string>() ?? "",
                            System = SelectedSystem,
                            PlayCount = obj["play_count"]?.GetValue<int>() ?? 0,
                            TotalTime = obj["total_time_display"]?.GetValue<string>() ?? "",
                            LastPlayed = obj["last_played"]?.GetValue<string>() ?? "",
                            AvgSession = obj["avg_session_display"]?.GetValue<string>() ?? "",
                        });
                    }
                }
                StatusText = $"{SelectedSystem}: {GameStats.Count} games tracked, {TotalPlays} total plays";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task LoadMostPlayedAsync()
    {
        IsLoading = true;
        StatusText = "Loading most-played leaderboard...";
        MostPlayed.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("rl_most_played", new { top_n = 50 });
            if (result is JsonObject r)
            {
                var leaders = r["leaderboard"]?.AsArray();
                if (leaders != null)
                {
                    foreach (var g in leaders)
                    {
                        if (g is not JsonObject obj) continue;
                        MostPlayed.Add(new RlGameStatsRow
                        {
                            Game = obj["game"]?.GetValue<string>() ?? "",
                            System = obj["system"]?.GetValue<string>() ?? "",
                            PlayCount = obj["play_count"]?.GetValue<int>() ?? 0,
                            TotalTime = obj["total_time_display"]?.GetValue<string>() ?? "",
                            LastPlayed = obj["last_played"]?.GetValue<string>() ?? "",
                        });
                    }
                }
                StatusText = $"Leaderboard: top {MostPlayed.Count} most-played games";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    // ═════════════════════════════════════════════════════════════════
    // M60 — Keymapper Profiles
    // ═════════════════════════════════════════════════════════════════

    [RelayCommand]
    public async Task LoadKeymappersAsync()
    {
        IsLoading = true;
        StatusText = "Scanning keymapper profiles...";
        Keymappers.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("rl_keymappers");
            if (result is JsonObject r)
            {
                TotalProfiles = r["total_profiles"]?.GetValue<int>() ?? 0;
                var profiles = r["profiles"]?.AsArray();
                if (profiles != null)
                {
                    foreach (var p in profiles)
                    {
                        if (p is not JsonObject obj) continue;
                        Keymappers.Add(new RlKeymapperRow
                        {
                            ProfileName = obj["profile_name"]?.GetValue<string>() ?? "",
                            KeymapperType = obj["keymapper_type"]?.GetValue<string>() ?? "",
                            System = obj["system"]?.GetValue<string>() ?? "",
                            MappingCount = obj["mapping_count"]?.GetValue<int>() ?? 0,
                            Status = obj["status"]?.GetValue<string>() ?? "OK",
                        });
                    }
                }
                StatusText = $"Keymappers: {TotalProfiles} profiles found";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    // ═════════════════════════════════════════════════════════════════
    // M60 — MultiGame Validation
    // ═════════════════════════════════════════════════════════════════

    [RelayCommand]
    public async Task LoadMultiGameAsync()
    {
        if (string.IsNullOrWhiteSpace(SelectedSystem)) { StatusText = "Enter a system name first."; return; }
        IsLoading = true;
        StatusText = $"Validating MultiGame for {SelectedSystem}...";
        MultiGames.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("rl_multigame", new { system = SelectedSystem });
            if (result is JsonObject r)
            {
                var entries = r["entries"]?.AsArray();
                if (entries != null)
                {
                    foreach (var e in entries)
                    {
                        if (e is not JsonObject obj) continue;
                        MultiGames.Add(new RlMultiGameRow
                        {
                            Game = obj["game"]?.GetValue<string>() ?? "",
                            DiscCount = obj["disc_count"]?.GetValue<int>() ?? 0,
                            Status = obj["status"]?.GetValue<string>() ?? "OK",
                        });
                    }
                }
                StatusText = $"MultiGame: {MultiGames.Count} entries for {SelectedSystem}";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    // ═════════════════════════════════════════════════════════════════
    // M60 — 7z Extraction Settings
    // ═════════════════════════════════════════════════════════════════

    [RelayCommand]
    public async Task LoadSevenZipAsync()
    {
        IsLoading = true;
        StatusText = "Checking 7z extraction settings...";
        SevenZipIssues.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("rl_7z_settings");
            if (result is JsonObject r)
            {
                SevenZipSettings = new Rl7zSettingsModel
                {
                    ExtractPath = r["extract_path"]?.GetValue<string>() ?? "",
                    TempDir = r["temp_dir"]?.GetValue<string>() ?? "",
                    ExtractPathExists = r["extract_path_exists"]?.GetValue<bool>() ?? false,
                    TempDirExists = r["temp_dir_exists"]?.GetValue<bool>() ?? false,
                    CacheSize = r["cache_size"]?.GetValue<string>() ?? "",
                    CleanupPolicy = r["cleanup_policy"]?.GetValue<string>() ?? "",
                    IssueCount = r["issues"]?.AsArray()?.Count ?? 0,
                };
                ParseIssues(r["issues"]?.AsArray(), SevenZipIssues);
                StatusText = $"7z settings loaded — {SevenZipSettings.IssueCount} issues";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    // ═════════════════════════════════════════════════════════════════
    // M60 — Full Integration Report
    // ═════════════════════════════════════════════════════════════════

    [RelayCommand]
    public async Task LoadIntegrationReportAsync()
    {
        IsLoading = true;
        StatusText = "Generating full RL integration report...";
        try
        {
            var result = await _mcp.CallToolAsync("rl_integration_report");
            if (result is JsonObject r)
            {
                // Stats summary
                var stats = r["stats_summary"]?.AsObject();
                if (stats != null)
                {
                    TotalPlays = stats["total_plays"]?.GetValue<int>() ?? 0;
                    TotalPlayTime = stats["total_time_display"]?.GetValue<string>() ?? "";
                }
                // Keymapper summary
                TotalProfiles = r["keymapper_summary"]?["total_profiles"]?.GetValue<int>() ?? 0;
                // 7z
                var sz = r["seven_zip"]?.AsObject();
                if (sz != null)
                {
                    SevenZipSettings = new Rl7zSettingsModel
                    {
                        ExtractPath = sz["extract_path"]?.GetValue<string>() ?? "",
                        CacheSize = sz["cache_size"]?.GetValue<string>() ?? "",
                        IssueCount = sz["issues"]?.AsArray()?.Count ?? 0,
                    };
                }
                StatusText = $"Integration report complete — {TotalPlays} plays, {TotalProfiles} profiles";
            }
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    // ── Helpers ──────────────────────────────────────────────────────

    private void ParseFade(JsonObject? fade)
    {
        var items = fade?["items"]?.AsArray();
        if (items == null) return;
        foreach (var f in items)
        {
            if (f is not JsonObject obj) continue;
            FadeItems.Add(new RlFadeRow
            {
                Game = obj["game"]?.GetValue<string>() ?? "",
                Layer = obj["layer"]?.GetValue<int>() ?? 1,
                FileName = obj["file_name"]?.GetValue<string>() ?? "",
                Dimensions = obj["dimensions"]?.GetValue<string>() ?? "",
                Status = obj["status"]?.GetValue<string>() ?? "OK",
            });
        }
    }

    private void ParseBezels(JsonObject? bezels)
    {
        var items = bezels?["items"]?.AsArray();
        if (items == null) return;
        foreach (var b in items)
        {
            if (b is not JsonObject obj) continue;
            BezelItems.Add(new RlBezelRow
            {
                Game = obj["game"]?.GetValue<string>() ?? "",
                FileName = obj["file_name"]?.GetValue<string>() ?? "",
                Dimensions = obj["dimensions"]?.GetValue<string>() ?? "",
                Orientation = obj["orientation"]?.GetValue<string>() ?? "",
                HasBackground = obj["has_background"]?.GetValue<bool>() ?? false,
                Status = obj["status"]?.GetValue<string>() ?? "OK",
            });
        }
    }

    private void ParsePause(JsonObject? pause)
    {
        var items = pause?["items"]?.AsArray();
        if (items == null) return;
        foreach (var p in items)
        {
            if (p is not JsonObject obj) continue;
            PauseItems.Add(new RlPauseRow
            {
                Game = obj["game"]?.GetValue<string>() ?? "",
                Category = obj["category"]?.GetValue<string>() ?? "",
                FileName = obj["file_name"]?.GetValue<string>() ?? "",
                FileType = obj["file_type"]?.GetValue<string>() ?? "",
            });
        }
    }

    private static void ParseIssues(JsonArray? issues, ObservableCollection<RlIssueRow> target)
    {
        if (issues == null) return;
        foreach (var i in issues)
        {
            if (i is not JsonObject obj) continue;
            target.Add(new RlIssueRow
            {
                Severity = obj["severity"]?.GetValue<string>() ?? "info",
                Message = obj["message"]?.GetValue<string>() ?? "",
                Source = obj["source"]?.GetValue<string>() ?? "",
            });
        }
    }
}
