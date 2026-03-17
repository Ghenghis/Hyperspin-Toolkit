using HyperSpinToolkit.ViewModels;

namespace HyperSpinToolkit.Views;

public partial class SettingsPage
{
    public SettingsViewModel ViewModel { get; }

    public SettingsPage(SettingsViewModel viewModel)
    {
        ViewModel = viewModel;
        DataContext = this;
        InitializeComponent();
    }
}
