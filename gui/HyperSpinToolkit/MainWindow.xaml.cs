using HyperSpinToolkit.Views;
using Wpf.Ui.Controls;

namespace HyperSpinToolkit;

public partial class MainWindow : FluentWindow
{
    public MainWindow()
    {
        InitializeComponent();
        // Let NavigationView resolve pages via DI on demand
        RootNavigation.SetServiceProvider(App.Services);
        Loaded += (_, _) => RootNavigation.Navigate(typeof(DashboardPage));
    }
}
