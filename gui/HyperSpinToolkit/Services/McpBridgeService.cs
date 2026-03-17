using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace HyperSpinToolkit.Services;

/// <summary>
/// Persistent JSON-RPC client for the Python mcp_bridge.py server.
/// Spawns python process once and reuses stdin/stdout for all calls.
/// </summary>
public class McpBridgeService : IDisposable
{
    private static readonly string ToolkitRoot = @"D:\hyperspin_toolkit";
    private static readonly string BridgeScript = Path.Combine(ToolkitRoot, "mcp_bridge.py");

    private Process? _process;
    private StreamWriter? _stdin;
    private StreamReader? _stdout;
    private int _nextId = 0;
    private readonly SemaphoreSlim _lock = new(1, 1);
    private bool _connected = false;

    public bool IsConnected => _connected;
    public string? LastError { get; private set; }
    public string PythonExe { get; set; } = "python";

    public async Task<bool> ConnectAsync()
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = PythonExe,
                Arguments = $"\"{BridgeScript}\"",
                WorkingDirectory = ToolkitRoot,
                UseShellExecute = false,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };

            _process = new Process { StartInfo = psi };
            _process.Start();

            _stdin = _process.StandardInput;
            _stdout = _process.StandardOutput;

            // MCP handshake
            var initResp = await SendRawAsync("initialize", new { protocolVersion = "2024-11-05" });
            _connected = initResp != null;

            if (_connected)
            {
                await SendRawAsync("notifications/initialized", null, noResponse: true);
            }

            return _connected;
        }
        catch (Exception ex)
        {
            LastError = ex.Message;
            _connected = false;
            return false;
        }
    }

    /// <summary>Call a named tool and return parsed result JSON, or null on error.</summary>
    public async Task<JsonNode?> CallToolAsync(string toolName, object? arguments = null)
    {
        var resp = await SendRawAsync("tools/call", new
        {
            name = toolName,
            arguments = arguments ?? new { }
        });

        if (resp == null) return null;

        var content = resp["result"]?["content"]?[0]?["text"]?.GetValue<string>();
        if (content == null) return null;

        try { return JsonNode.Parse(content); }
        catch { return JsonValue.Create(content); }
    }

    /// <summary>Get the list of all available MCP tools.</summary>
    public async Task<List<string>> ListToolsAsync()
    {
        var resp = await SendRawAsync("tools/list", null);
        var tools = resp?["result"]?["tools"]?.AsArray();
        if (tools == null) return [];
        return tools.Select(t => t?["name"]?.GetValue<string>() ?? "").Where(n => n != "").ToList();
    }

    private async Task<JsonNode?> SendRawAsync(string method, object? @params, bool noResponse = false)
    {
        if (!noResponse && method != "initialize" && !_connected && method != "initialize")
            return null;

        await _lock.WaitAsync();
        try
        {
            if (_stdin == null || _stdout == null) return null;

            var id = Interlocked.Increment(ref _nextId);
            var request = new Dictionary<string, object?>
            {
                ["jsonrpc"] = "2.0",
                ["id"] = id,
                ["method"] = method,
            };
            if (@params != null)
                request["params"] = @params;

            var json = JsonSerializer.Serialize(request);
            await _stdin.WriteLineAsync(json);
            await _stdin.FlushAsync();

            if (noResponse) return null;

            var responseLine = await _stdout.ReadLineAsync();
            if (responseLine == null) return null;

            return JsonNode.Parse(responseLine);
        }
        catch (Exception ex)
        {
            LastError = ex.Message;
            return null;
        }
        finally
        {
            _lock.Release();
        }
    }

    public void Dispose()
    {
        try
        {
            _stdin?.Close();
            _stdout?.Close();
            _process?.Kill();
            _process?.Dispose();
        }
        catch { }
        _connected = false;
    }
}
