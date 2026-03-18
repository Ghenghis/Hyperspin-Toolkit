using System;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace HyperSpinToolkit.Controls
{
    /// <summary>
    /// Animated arcade boot sequence splash screen with sequential log lines,
    /// neon progress bar, and fade-in title animation.
    /// </summary>
    public partial class ArcadeSplashScreen : Window
    {
        private readonly string[] _bootLines = new[]
        {
            "[OK] XINPUT GAMEPAD SUBSYSTEM",
            "[OK] NEON THEME ENGINE v2.0",
            "[OK] PARTICLE SYSTEM (AmbientStars, NeonRain)",
            "[OK] CRT SCANLINE SHADER",
            "[OK] SOUND EFFECTS ENGINE",
            "[OK] VIDEO BACKGROUND RENDERER",
            "[OK] MCP BRIDGE CONNECTING...",
            "[OK] ARCADE CONTROLS LOADED",
            "[OK] 59/66 MILESTONES VERIFIED",
            "[OK] ALL SYSTEMS NOMINAL",
        };

        private int _currentLine;
        private double _progressTarget;
        private readonly DispatcherTimer _bootTimer;

        public ArcadeSplashScreen()
        {
            InitializeComponent();

            _bootTimer = new DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(180)
            };
            _bootTimer.Tick += OnBootTick;

            Loaded += OnSplashLoaded;
        }

        private void OnSplashLoaded(object sender, RoutedEventArgs e)
        {
            // Fade in title
            var titleFade = new DoubleAnimation(0, 1, new Duration(TimeSpan.FromMilliseconds(600)))
            {
                EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut }
            };
            TitleText.BeginAnimation(OpacityProperty, titleFade);

            // Fade in subtitle after delay
            var subtitleFade = new DoubleAnimation(0, 1, new Duration(TimeSpan.FromMilliseconds(400)))
            {
                BeginTime = TimeSpan.FromMilliseconds(400),
                EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut }
            };
            SubtitleText.BeginAnimation(OpacityProperty, subtitleFade);

            // Start boot sequence after a beat
            _bootTimer.Interval = TimeSpan.FromMilliseconds(800);
            _bootTimer.Start();
        }

        private void OnBootTick(object? sender, EventArgs e)
        {
            // After first tick, switch to faster interval
            _bootTimer.Interval = TimeSpan.FromMilliseconds(180);

            if (_currentLine < _bootLines.Length)
            {
                // Append boot line
                BootLog.Text += (_currentLine > 0 ? "\n" : "") + _bootLines[_currentLine];
                _currentLine++;

                // Animate progress bar
                _progressTarget = ((double)_currentLine / _bootLines.Length) * 560; // max width
                var widthAnim = new DoubleAnimation(ProgressFill.Width, _progressTarget,
                    new Duration(TimeSpan.FromMilliseconds(150)));
                ProgressFill.BeginAnimation(WidthProperty, widthAnim);

                StatusText.Text = $"LOADING MODULE {_currentLine}/{_bootLines.Length}...";
            }
            else
            {
                _bootTimer.Stop();
                StatusText.Text = "BOOT COMPLETE — LAUNCHING TOOLKIT";

                // Brief pause then close
                var closeTimer = new DispatcherTimer
                {
                    Interval = TimeSpan.FromMilliseconds(600)
                };
                closeTimer.Tick += (_, _) =>
                {
                    closeTimer.Stop();

                    // Fade out
                    var fadeOut = new DoubleAnimation(1, 0, new Duration(TimeSpan.FromMilliseconds(400)));
                    fadeOut.Completed += (_, _) => Close();
                    BeginAnimation(OpacityProperty, fadeOut);
                };
                closeTimer.Start();
            }
        }

        /// <summary>
        /// Show the splash screen and return a Task that completes when it closes.
        /// Call from App.OnStartup before showing MainWindow.
        /// </summary>
        public static Task ShowSplashAsync()
        {
            var tcs = new TaskCompletionSource();
            var splash = new ArcadeSplashScreen();
            splash.Closed += (_, _) => tcs.SetResult();
            splash.Show();
            return tcs.Task;
        }
    }
}
