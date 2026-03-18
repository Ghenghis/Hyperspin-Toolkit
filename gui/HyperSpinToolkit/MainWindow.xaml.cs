using System;
using System.Windows;
using HyperSpinToolkit.Services;
using HyperSpinToolkit.Views;
using Wpf.Ui.Controls;

namespace HyperSpinToolkit;

public partial class MainWindow : FluentWindow
{
    private readonly Type[] _pageOrder = new[]
    {
        typeof(DashboardPage),
        typeof(CollectionBrowserPage),
        typeof(AssetGalleryPage),
        typeof(DrivesPage),
        typeof(AuditPage),
        typeof(BackupPage),
        typeof(AgentConsolePage),
        typeof(AIChatPage),
    };
    private int _currentPageIndex;

    public MainWindow()
    {
        InitializeComponent();
        RootNavigation.SetServiceProvider(App.Services);

        Loaded += OnWindowLoaded;
        Closed += OnWindowClosed;
    }

    private void OnWindowLoaded(object sender, RoutedEventArgs e)
    {
        RootNavigation.Navigate(typeof(DashboardPage));
        _currentPageIndex = 0;

        // Load and apply gamepad config
        var config = ButtonMappingConfig.Load();
        ButtonMappingConfig.Apply(config);

        // Wire gamepad actions
        var input = ArcadeInputHandler.Instance;
        input.ActionTriggered += OnArcadeAction;
        input.Start();

        // Welcome notification
        HudBar.PushNotification("HYPERSPIN EXTREME TOOLKIT v2.0 — 59/66 MILESTONES COMPLETE — GAMEPAD READY");
    }

    private void OnWindowClosed(object? sender, EventArgs e)
    {
        ArcadeInputHandler.Instance.Stop();
        ArcadeInputHandler.Instance.Dispose();
    }

    private void OnArcadeAction(object? sender, ArcadeInputEventArgs e)
    {
        Dispatcher.Invoke(() =>
        {
            switch (e.Action)
            {
                case ArcadeAction.PreviousPage:
                    NavigateRelative(-1);
                    break;
                case ArcadeAction.NextPage:
                    NavigateRelative(1);
                    break;
                case ArcadeAction.OpenSettings:
                    NavigateToPage(typeof(SettingsPage));
                    break;
                case ArcadeAction.ToggleChatOverlay:
                    NavigateToPage(typeof(AIChatPage));
                    break;
            }
        });
    }

    private void NavigateRelative(int delta)
    {
        int newIndex = _currentPageIndex + delta;
        if (newIndex < 0) newIndex = _pageOrder.Length - 1;
        if (newIndex >= _pageOrder.Length) newIndex = 0;

        var targetPage = _pageOrder[newIndex];

        // Play page transition
        var transitions = PageTransitionService.Instance;
        var style = delta < 0 ? TransitionStyle.SlideRight : TransitionStyle.SlideLeft;
        transitions.PlayTransition(RootNavigation, style, () =>
        {
            RootNavigation.Navigate(targetPage);
        });

        _currentPageIndex = newIndex;
        HudBar.PushNotification($"PAGE {newIndex + 1}/{_pageOrder.Length}: {targetPage.Name.Replace("Page", "").ToUpperInvariant()}");
    }

    private void NavigateToPage(Type pageType)
    {
        int idx = Array.IndexOf(_pageOrder, pageType);

        var transitions = PageTransitionService.Instance;
        transitions.PlayTransition(RootNavigation, TransitionStyle.PixelDissolve, () =>
        {
            RootNavigation.Navigate(pageType);
        });

        if (idx >= 0)
            _currentPageIndex = idx;
    }
}
