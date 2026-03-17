using HyperSpinToolkit.ViewModels;

namespace HyperSpinToolkit.Views;

public partial class DrivesPage
{
    public DrivesViewModel ViewModel { get; }

    public DrivesPage(DrivesViewModel viewModel)
    {
        ViewModel = viewModel;
        DataContext = this;
        InitializeComponent();
        Loaded += async (_, _) => await ViewModel.LoadStatusAsync();
    }
}
