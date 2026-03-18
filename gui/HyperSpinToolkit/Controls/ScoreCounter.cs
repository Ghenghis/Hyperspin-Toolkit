using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace HyperSpinToolkit.Controls
{
    /// <summary>
    /// M45 — ScoreCounter: Animated number roller with digit-by-digit cascade animation.
    /// Use for stat counters on the dashboard (total ROMs, games, assets, etc.).
    /// </summary>
    public class ScoreCounter : Control
    {
        private double _displayValue;
        private DispatcherTimer? _animTimer;

        static ScoreCounter()
        {
            DefaultStyleKeyProperty.OverrideMetadata(typeof(ScoreCounter),
                new FrameworkPropertyMetadata(typeof(ScoreCounter)));
        }

        public static readonly DependencyProperty TargetValueProperty =
            DependencyProperty.Register(nameof(TargetValue), typeof(double), typeof(ScoreCounter),
                new FrameworkPropertyMetadata(0.0, FrameworkPropertyMetadataOptions.AffectsRender, OnTargetValueChanged));

        public static readonly DependencyProperty PrefixProperty =
            DependencyProperty.Register(nameof(Prefix), typeof(string), typeof(ScoreCounter),
                new PropertyMetadata(""));

        public static readonly DependencyProperty SuffixProperty =
            DependencyProperty.Register(nameof(Suffix), typeof(string), typeof(ScoreCounter),
                new PropertyMetadata(""));

        public static readonly DependencyProperty DigitColorProperty =
            DependencyProperty.Register(nameof(DigitColor), typeof(Brush), typeof(ScoreCounter),
                new PropertyMetadata(new SolidColorBrush(Color.FromRgb(0xFF, 0xF0, 0x00))));

        public static readonly DependencyProperty LabelColorProperty =
            DependencyProperty.Register(nameof(LabelColor), typeof(Brush), typeof(ScoreCounter),
                new PropertyMetadata(new SolidColorBrush(Color.FromRgb(0x00, 0xD4, 0xFF))));

        public static readonly DependencyProperty DigitFontSizeProperty =
            DependencyProperty.Register(nameof(DigitFontSize), typeof(double), typeof(ScoreCounter),
                new PropertyMetadata(28.0));

        public static readonly DependencyProperty FormatStringProperty =
            DependencyProperty.Register(nameof(FormatString), typeof(string), typeof(ScoreCounter),
                new PropertyMetadata("N0"));

        public static readonly DependencyProperty AnimationSpeedProperty =
            DependencyProperty.Register(nameof(AnimationSpeed), typeof(double), typeof(ScoreCounter),
                new PropertyMetadata(30.0)); // ms per frame

        public double TargetValue
        {
            get => (double)GetValue(TargetValueProperty);
            set => SetValue(TargetValueProperty, value);
        }

        public string Prefix
        {
            get => (string)GetValue(PrefixProperty);
            set => SetValue(PrefixProperty, value);
        }

        public string Suffix
        {
            get => (string)GetValue(SuffixProperty);
            set => SetValue(SuffixProperty, value);
        }

        public Brush DigitColor
        {
            get => (Brush)GetValue(DigitColorProperty);
            set => SetValue(DigitColorProperty, value);
        }

        public Brush LabelColor
        {
            get => (Brush)GetValue(LabelColorProperty);
            set => SetValue(LabelColorProperty, value);
        }

        public double DigitFontSize
        {
            get => (double)GetValue(DigitFontSizeProperty);
            set => SetValue(DigitFontSizeProperty, value);
        }

        public string FormatString
        {
            get => (string)GetValue(FormatStringProperty);
            set => SetValue(FormatStringProperty, value);
        }

        public double AnimationSpeed
        {
            get => (double)GetValue(AnimationSpeedProperty);
            set => SetValue(AnimationSpeedProperty, value);
        }

        private static void OnTargetValueChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is ScoreCounter counter)
                counter.StartRollAnimation();
        }

        private void StartRollAnimation()
        {
            _animTimer?.Stop();
            _animTimer = new DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(AnimationSpeed)
            };
            _animTimer.Tick += AnimTimer_Tick;
            _animTimer.Start();
        }

        private void AnimTimer_Tick(object? sender, EventArgs e)
        {
            double diff = TargetValue - _displayValue;
            if (Math.Abs(diff) < 0.5)
            {
                _displayValue = TargetValue;
                _animTimer?.Stop();
            }
            else
            {
                // Ease toward target
                _displayValue += diff * 0.15;
            }
            InvalidateVisual();
        }

        protected override void OnRender(DrawingContext dc)
        {
            base.OnRender(dc);

            string digits = _displayValue.ToString(FormatString);
            string display = $"{Prefix}{digits}{Suffix}";

            var typeface = new Typeface(
                new FontFamily("Consolas, JetBrains Mono"),
                FontStyles.Normal, FontWeights.Bold, FontStretches.Normal);

            var text = new FormattedText(
                display,
                System.Globalization.CultureInfo.CurrentCulture,
                FlowDirection.LeftToRight,
                typeface,
                DigitFontSize,
                DigitColor,
                VisualTreeHelper.GetDpi(this).PixelsPerDip);

            double x = (ActualWidth - text.Width) / 2;
            double y = (ActualHeight - text.Height) / 2;
            dc.DrawText(text, new Point(Math.Max(0, x), Math.Max(0, y)));
        }

        protected override Size MeasureOverride(Size availableSize)
        {
            return new Size(
                Math.Min(availableSize.Width, 200),
                Math.Min(availableSize.Height, DigitFontSize + 8));
        }
    }
}
