using HyperSpinToolkit.ViewModels;

namespace HyperSpinToolkit.Views;

public partial class AuditPage
{
    public AuditViewModel ViewModel { get; }

    public AuditPage(AuditViewModel viewModel)
    {
        ViewModel = viewModel;
        DataContext = this;
        InitializeComponent();
    }
}
