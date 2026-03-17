using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using HyperSpinToolkit.Services;

namespace HyperSpinToolkit.ViewModels;

public partial class SettingsViewModel : ObservableObject
{
    private readonly McpBridgeService _mcp;

    [ObservableProperty] private string _toolkitRoot = @"D:\hyperspin_toolkit";
    [ObservableProperty] private string _pythonExe = "python";
    [ObservableProperty] private string _configPath = @"D:\hyperspin_toolkit\config.yaml";
    [ObservableProperty] private string _statusText = "";
    [ObservableProperty] private bool _isDark = true;
    [ObservableProperty] private string _bridgeStatus = "";
    [ObservableProperty] private string _availableTools = "";

    public SettingsViewModel(McpBridgeService mcp)
    {
        _mcp = mcp;
        PythonExe = mcp.PythonExe;
        RefreshBridgeStatus();
    }

    private void RefreshBridgeStatus()
    {
        BridgeStatus = _mcp.IsConnected
            ? "MCP Bridge: Connected"
            : $"MCP Bridge: Offline — {_mcp.LastError ?? "not started"}";
    }

    [RelayCommand]
    public async Task ReconnectBridgeAsync()
    {
        StatusText = "Reconnecting MCP bridge...";
        _mcp.PythonExe = PythonExe;
        _mcp.Dispose();
        var ok = await _mcp.ConnectAsync();
        RefreshBridgeStatus();
        StatusText = ok ? "✓ Bridge reconnected" : $"✗ Failed: {_mcp.LastError}";
    }

    [RelayCommand]
    public async Task ListToolsAsync()
    {
        StatusText = "Fetching tool list...";
        var tools = await _mcp.ListToolsAsync();
        AvailableTools = tools.Count == 0
            ? "No tools found (bridge offline?)"
            : string.Join("\n", tools.Select((t, i) => $"  {i + 1:D2}. {t}"));
        StatusText = $"{tools.Count} tools available";
    }
}
