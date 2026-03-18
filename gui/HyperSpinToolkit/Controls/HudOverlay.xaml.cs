using System;
using System.Collections.Concurrent;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace HyperSpinToolkit.Controls
{
    /// <summary>
    /// Persistent bottom HUD bar with agent status LEDs, drive health gauge,
    /// gamepad connection indicator, marquee notifications, and system clock.
    /// </summary>
    public partial class HudOverlay : UserControl
    {
        private readonly DispatcherTimer _clockTimer;
        private readonly DispatcherTimer _marqueeTimer;
        private readonly ConcurrentQueue<string> _notificationQueue = new();
        private bool _marqueeAnimating;
        private double _marqueeWidth;

        public HudOverlay()
        {
            InitializeComponent();

            // Clock tick every second
            _clockTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
            _clockTimer.Tick += (_, _) => ClockText.Text = DateTime.Now.ToString("HH:mm:ss");
            _clockTimer.Start();
            ClockText.Text = DateTime.Now.ToString("HH:mm:ss");

            // Marquee check every 3 seconds
            _marqueeTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(3) };
            _marqueeTimer.Tick += OnMarqueeCheck;
            _marqueeTimer.Start();

            Loaded += OnLoaded;
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            // Wire up gamepad connection events
            try
            {
                var input = Services.ArcadeInputHandler.Instance;
                input.ConnectionChanged += (_, args) =>
                {
                    Dispatcher.Invoke(() =>
                    {
                        LedGamepad.LedState = args.Connected ? "Green" : "Off";
                        if (args.Connected)
                            PushNotification($"PLAYER {args.PlayerIndex + 1} GAMEPAD CONNECTED");
                    });
                };
            }
            catch { /* Input handler not available */ }
        }

        /// <summary>
        /// Push a notification message to the marquee scroll queue.
        /// </summary>
        public void PushNotification(string message)
        {
            if (!string.IsNullOrWhiteSpace(message))
                _notificationQueue.Enqueue(message);
        }

        /// <summary>
        /// Update agent LED states from external code.
        /// </summary>
        public void SetAgentLed(string agent, string state)
        {
            Dispatcher.Invoke(() =>
            {
                switch (agent.ToUpperInvariant())
                {
                    case "BRIDGE": case "BRG": LedBridge.LedState = state; break;
                    case "GOOSE": case "GSE": LedGoose.LedState = state; break;
                    case "NEMO": case "NMC": case "NEMOCLAW": LedNemo.LedState = state; break;
                }
            });
        }

        /// <summary>
        /// Update drive health gauge value (0–100).
        /// </summary>
        public void SetDriveHealth(double value)
        {
            Dispatcher.Invoke(() => DriveGauge.Value = Math.Clamp(value, 0, 100));
        }

        private void OnMarqueeCheck(object? sender, EventArgs e)
        {
            if (_marqueeAnimating) return;

            if (_notificationQueue.TryDequeue(out string? message) && message != null)
            {
                StartMarqueeAnimation(message);
            }
        }

        private void StartMarqueeAnimation(string text)
        {
            _marqueeAnimating = true;
            MarqueeText.Text = text;

            // Measure text width
            MarqueeText.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
            _marqueeWidth = MarqueeText.DesiredSize.Width;

            // Get canvas width
            var canvas = MarqueeText.Parent as Canvas;
            double canvasWidth = canvas?.ActualWidth ?? 600;

            // Animate from right edge to past left edge
            double startX = canvasWidth + 20;
            double endX = -_marqueeWidth - 20;
            double distance = startX - endX;
            double speed = 80; // pixels per second
            double durationSeconds = distance / speed;

            MarqueeTranslate.X = startX;

            var animation = new DoubleAnimation(startX, endX,
                new Duration(TimeSpan.FromSeconds(durationSeconds)))
            {
                EasingFunction = null // Linear scroll
            };
            animation.Completed += (_, _) => _marqueeAnimating = false;

            MarqueeTranslate.BeginAnimation(
                System.Windows.Media.TranslateTransform.XProperty, animation);
        }
    }
}
