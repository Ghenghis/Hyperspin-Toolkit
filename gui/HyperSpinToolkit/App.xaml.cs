using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using HyperSpinToolkit.Services;
using HyperSpinToolkit.ViewModels;
using HyperSpinToolkit.Views;

namespace HyperSpinToolkit;

public partial class App : Application
{
    public static IServiceProvider Services { get; private set; } = null!;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        var services = new ServiceCollection();
        ConfigureServices(services);
        Services = services.BuildServiceProvider();

        // Start MCP bridge in background — don't block startup
        var mcp = Services.GetRequiredService<McpBridgeService>();
        _ = mcp.ConnectAsync();

        var mainWindow = Services.GetRequiredService<MainWindow>();
        mainWindow.Show();
    }

    private static void ConfigureServices(IServiceCollection services)
    {
        // Core backend service (singleton — one persistent Python process)
        services.AddSingleton<McpBridgeService>();

        // ViewModels — transient so each page navigation gets fresh state
        services.AddTransient<DashboardViewModel>();
        services.AddTransient<DrivesViewModel>();
        services.AddTransient<AuditViewModel>();
        services.AddTransient<BackupViewModel>();
        services.AddTransient<SettingsViewModel>();

        // Pages — transient, resolved lazily by NavigationView via SetServiceProvider
        services.AddTransient<DashboardPage>();
        services.AddTransient<DrivesPage>();
        services.AddTransient<AuditPage>();
        services.AddTransient<BackupPage>();
        services.AddTransient<SettingsPage>();

        // Main window singleton
        services.AddSingleton<MainWindow>();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        Services.GetService<McpBridgeService>()?.Dispose();
        base.OnExit(e);
    }
}
