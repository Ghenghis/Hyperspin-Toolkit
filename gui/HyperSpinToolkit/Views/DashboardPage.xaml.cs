using HyperSpinToolkit.ViewModels;

namespace HyperSpinToolkit.Views;

public partial class DashboardPage
{
    public DashboardViewModel ViewModel { get; }

    public DashboardPage(DashboardViewModel viewModel)
    {
        ViewModel = viewModel;
        DataContext = this;
        InitializeComponent();
        Loaded += async (_, _) => await ViewModel.RefreshAsync();
    }
}
