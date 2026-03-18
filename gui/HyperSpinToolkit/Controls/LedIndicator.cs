using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Effects;

namespace HyperSpinToolkit.Controls
{
    /// <summary>
    /// M45 — LedIndicator: Multi-color LED with glow states (green/yellow/red/off).
    /// Use for agent status, drive health, connection indicators.
    /// </summary>
    public class LedIndicator : Control
    {
        static LedIndicator()
        {
            DefaultStyleKeyProperty.OverrideMetadata(typeof(LedIndicator),
                new FrameworkPropertyMetadata(typeof(LedIndicator)));
        }

        public static readonly DependencyProperty LedStateProperty =
            DependencyProperty.Register(nameof(LedState), typeof(LedState), typeof(LedIndicator),
                new FrameworkPropertyMetadata(LedState.Off, FrameworkPropertyMetadataOptions.AffectsRender));

        public static readonly DependencyProperty LedSizeProperty =
            DependencyProperty.Register(nameof(LedSize), typeof(double), typeof(LedIndicator),
                new PropertyMetadata(16.0));

        public static readonly DependencyProperty LabelTextProperty =
            DependencyProperty.Register(nameof(LabelText), typeof(string), typeof(LedIndicator),
                new PropertyMetadata(""));

        public LedState LedState
        {
            get => (LedState)GetValue(LedStateProperty);
            set => SetValue(LedStateProperty, value);
        }

        public double LedSize
        {
            get => (double)GetValue(LedSizeProperty);
            set => SetValue(LedSizeProperty, value);
        }

        public string LabelText
        {
            get => (string)GetValue(LabelTextProperty);
            set => SetValue(LabelTextProperty, value);
        }

        protected override void OnRender(DrawingContext dc)
        {
            base.OnRender(dc);

            double s = LedSize;
            var center = new Point(s / 2 + 2, ActualHeight / 2);

            Color ledColor = LedState switch
            {
                LedState.Green => Color.FromRgb(0x39, 0xFF, 0x14),
                LedState.Yellow => Color.FromRgb(0xFF, 0xF0, 0x00),
                LedState.Red => Color.FromRgb(0xFF, 0x17, 0x44),
                LedState.Blue => Color.FromRgb(0x00, 0xD4, 0xFF),
                LedState.Orange => Color.FromRgb(0xFF, 0x6E, 0x00),
                _ => Color.FromRgb(0x33, 0x33, 0x44),
            };

            // Outer glow
            if (LedState != LedState.Off)
            {
                var glowBrush = new RadialGradientBrush(
                    Color.FromArgb(0x60, ledColor.R, ledColor.G, ledColor.B),
                    Colors.Transparent);
                dc.DrawEllipse(glowBrush, null, center, s * 0.8, s * 0.8);
            }

            // LED body
            var bodyBrush = new RadialGradientBrush(
                Color.FromArgb(0xFF, (byte)System.Math.Min(ledColor.R + 60, 255),
                    (byte)System.Math.Min(ledColor.G + 60, 255),
                    (byte)System.Math.Min(ledColor.B + 60, 255)),
                ledColor);
            dc.DrawEllipse(bodyBrush, new Pen(new SolidColorBrush(
                Color.FromArgb(0x40, 0xFF, 0xFF, 0xFF)), 0.5), center, s / 2, s / 2);

            // Label text
            if (!string.IsNullOrEmpty(LabelText))
            {
                var text = new FormattedText(
                    LabelText,
                    System.Globalization.CultureInfo.CurrentCulture,
                    FlowDirection.LeftToRight,
                    new Typeface("Segoe UI"),
                    11,
                    new SolidColorBrush(Color.FromRgb(0xE0, 0xE0, 0xFF)),
                    VisualTreeHelper.GetDpi(this).PixelsPerDip);
                dc.DrawText(text, new Point(s + 8, center.Y - text.Height / 2));
            }
        }

        protected override Size MeasureOverride(Size availableSize)
        {
            double textWidth = string.IsNullOrEmpty(LabelText) ? 0 : LabelText.Length * 7 + 12;
            return new Size(LedSize + 4 + textWidth, System.Math.Max(LedSize + 4, 20));
        }
    }

    public enum LedState
    {
        Off,
        Green,
        Yellow,
        Red,
        Blue,
        Orange
    }
}
