using System;
using System.Windows;
using System.Windows.Controls;
using HyperSpinToolkit.Controls;
using HyperSpinToolkit.Services;
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
        Loaded += OnPageLoaded;
    }

    private void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        // Show config file path
        GamepadConfigPath.Text = $"Config: {ButtonMappingConfig.GetConfigPath()}";

        // Reflect current gamepad connection state
        var input = ArcadeInputHandler.Instance;
        GamepadLed.LedState = input.AnyConnected ? LedState.Green : LedState.Off;
        GamepadStatusText.Text = input.AnyConnected ? "Gamepad connected" : "No gamepad detected";

        // Load current transition settings
        var transitions = PageTransitionService.Instance;
        foreach (ComboBoxItem item in TransitionPicker.Items)
        {
            if (item.Tag?.ToString() == transitions.DefaultStyle.ToString())
            {
                TransitionPicker.SelectedItem = item;
                break;
            }
        }
        TransitionSpeedSlider.Value = transitions.Duration.TotalMilliseconds;
    }

    private void OnSaveGamepadConfig(object sender, RoutedEventArgs e)
    {
        // Read UI values and save
        var config = ButtonMappingConfig.CaptureCurrentConfig();

        if (TransitionPicker.SelectedItem is ComboBoxItem selected)
            config.TransitionStyle = selected.Tag?.ToString() ?? "PixelDissolve";

        config.TransitionDurationMs = (int)TransitionSpeedSlider.Value;
        config.VibrationEnabled = VibrationCheck.IsChecked == true;

        ButtonMappingConfig.Save(config);
        ButtonMappingConfig.Apply(config);
    }

    private void OnResetGamepadConfig(object sender, RoutedEventArgs e)
    {
        ButtonMappingConfig.ResetToDefaults();

        // Refresh UI
        TransitionPicker.SelectedIndex = 0;
        TransitionSpeedSlider.Value = 400;
        VibrationCheck.IsChecked = true;
    }
}
