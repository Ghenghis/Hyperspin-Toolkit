using HyperSpinToolkit.ViewModels;

namespace HyperSpinToolkit.Views;

public partial class RocketLauncherPage
{
    public RocketLauncherViewModel ViewModel { get; }

    public RocketLauncherPage(RocketLauncherViewModel viewModel)
    {
        ViewModel = viewModel;
        DataContext = this;
        InitializeComponent();
    }
}
