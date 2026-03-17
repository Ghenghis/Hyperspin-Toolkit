using HyperSpinToolkit.ViewModels;

namespace HyperSpinToolkit.Views;

public partial class BackupPage
{
    public BackupViewModel ViewModel { get; }

    public BackupPage(BackupViewModel viewModel)
    {
        ViewModel = viewModel;
        DataContext = this;
        InitializeComponent();
        Loaded += async (_, _) => await ViewModel.LoadBackupsAsync();
    }
}
