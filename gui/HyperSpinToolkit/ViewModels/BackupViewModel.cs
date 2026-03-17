using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using HyperSpinToolkit.Models;
using HyperSpinToolkit.Services;
using System.Collections.ObjectModel;
using System.Text.Json.Nodes;

namespace HyperSpinToolkit.ViewModels;

public partial class BackupViewModel : ObservableObject
{
    private readonly McpBridgeService _mcp;

    [ObservableProperty] private bool _isLoading = false;
    [ObservableProperty] private string _statusText = "Ready";
    [ObservableProperty] private ObservableCollection<BackupRow> _backups = [];

    // Create backup
    [ObservableProperty] private string _backupSource = "";
    [ObservableProperty] private string _backupLabel = "manual";
    [ObservableProperty] private string _backupType = "full";
    [ObservableProperty] private string _createResult = "";

    // Restore
    [ObservableProperty] private BackupRow? _selectedBackup;
    [ObservableProperty] private string _restoreTarget = "";
    [ObservableProperty] private string _restoreResult = "";

    public string[] BackupTypes => ["full", "incremental"];

    public BackupViewModel(McpBridgeService mcp) => _mcp = mcp;

    [RelayCommand]
    public async Task LoadBackupsAsync()
    {
        IsLoading = true;
        StatusText = "Loading backup history...";
        Backups.Clear();
        try
        {
            var result = await _mcp.CallToolAsync("backup_list");
            if (result is JsonArray arr)
            {
                foreach (var b in arr)
                {
                    if (b is not JsonObject obj) continue;
                    var sizeBytes = obj["size_bytes"]?.GetValue<long>() ?? 0;
                    Backups.Add(new BackupRow
                    {
                        Id = obj["id"]?.GetValue<int>() ?? 0,
                        BackupType = obj["backup_type"]?.GetValue<string>() ?? "",
                        Target = obj["target"]?.GetValue<string>() ?? "",
                        FileCount = obj["file_count"]?.GetValue<int>() ?? 0,
                        SizeMb = $"{sizeBytes / 1048576.0:F1} MB",
                        Status = obj["status"]?.GetValue<string>() ?? "",
                        CreatedAt = obj["created_at"]?.GetValue<string>() ?? "",
                    });
                }
            }
            StatusText = $"{Backups.Count} backups found";
        }
        catch (Exception ex) { StatusText = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task CreateBackupAsync()
    {
        if (string.IsNullOrWhiteSpace(BackupSource)) { CreateResult = "Enter source path first."; return; }
        IsLoading = true;
        CreateResult = $"Creating {BackupType} backup of {BackupSource}...";
        try
        {
            var result = await _mcp.CallToolAsync("backup_create", new
            {
                source = BackupSource,
                label = BackupLabel,
                backup_type = BackupType,
            });
            if (result is JsonObject r)
            {
                CreateResult = $"✓ Backup created — {r["file_count"]?.GetValue<int>() ?? 0:N0} files\n" +
                               $"Location: {r["archive_path"]?.GetValue<string>() ?? "?"}";
            }
            await LoadBackupsAsync();
            StatusText = "Backup created successfully";
        }
        catch (Exception ex) { CreateResult = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    public async Task RestoreBackupAsync()
    {
        if (SelectedBackup == null) { RestoreResult = "Select a backup from the list first."; return; }
        if (string.IsNullOrWhiteSpace(RestoreTarget)) { RestoreResult = "Enter restore target path."; return; }

        IsLoading = true;
        RestoreResult = $"Restoring backup {SelectedBackup.Id}...";
        try
        {
            var result = await _mcp.CallToolAsync("backup_rollback", new { backup_id = SelectedBackup.Id });
            if (result is JsonObject r)
            {
                RestoreResult = $"✓ Restored {r["restored"]?.GetValue<int>() ?? 0:N0} files";
            }
            StatusText = "Restore complete";
        }
        catch (Exception ex) { RestoreResult = $"Error: {ex.Message}"; }
        finally { IsLoading = false; }
    }
}
