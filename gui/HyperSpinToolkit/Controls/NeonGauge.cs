using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;

namespace HyperSpinToolkit.Controls
{
    /// <summary>
    /// M45 — NeonGauge: Arcade-style circular/bar meter for health %, drive usage, completion.
    /// Supports both circular and horizontal bar modes with neon glow.
    /// </summary>
    public class NeonGauge : Control
    {
        static NeonGauge()
        {
            DefaultStyleKeyProperty.OverrideMetadata(typeof(NeonGauge),
                new FrameworkPropertyMetadata(typeof(NeonGauge)));
        }

        // ── Dependency Properties ──

        public static readonly DependencyProperty ValueProperty =
            DependencyProperty.Register(nameof(Value), typeof(double), typeof(NeonGauge),
                new FrameworkPropertyMetadata(0.0, FrameworkPropertyMetadataOptions.AffectsRender, OnValueChanged));

        public static readonly DependencyProperty MinimumProperty =
            DependencyProperty.Register(nameof(Minimum), typeof(double), typeof(NeonGauge),
                new PropertyMetadata(0.0));

        public static readonly DependencyProperty MaximumProperty =
            DependencyProperty.Register(nameof(Maximum), typeof(double), typeof(NeonGauge),
                new PropertyMetadata(100.0));

        public static readonly DependencyProperty GaugeColorProperty =
            DependencyProperty.Register(nameof(GaugeColor), typeof(Brush), typeof(NeonGauge),
                new PropertyMetadata(new SolidColorBrush(Color.FromRgb(0x00, 0xD4, 0xFF))));

        public static readonly DependencyProperty TrackColorProperty =
            DependencyProperty.Register(nameof(TrackColor), typeof(Brush), typeof(NeonGauge),
                new PropertyMetadata(new SolidColorBrush(Color.FromRgb(0x22, 0x22, 0x40))));

        public static readonly DependencyProperty GaugeModeProperty =
            DependencyProperty.Register(nameof(GaugeMode), typeof(GaugeDisplayMode), typeof(NeonGauge),
                new PropertyMetadata(GaugeDisplayMode.Circular));

        public static readonly DependencyProperty LabelProperty =
            DependencyProperty.Register(nameof(Label), typeof(string), typeof(NeonGauge),
                new PropertyMetadata(""));

        public static readonly DependencyProperty ShowPercentageProperty =
            DependencyProperty.Register(nameof(ShowPercentage), typeof(bool), typeof(NeonGauge),
                new PropertyMetadata(true));

        public static readonly DependencyProperty StrokeThicknessProperty =
            DependencyProperty.Register(nameof(StrokeThickness), typeof(double), typeof(NeonGauge),
                new PropertyMetadata(6.0));

        public static readonly DependencyProperty AnimateDurationProperty =
            DependencyProperty.Register(nameof(AnimateDuration), typeof(Duration), typeof(NeonGauge),
                new PropertyMetadata(new Duration(TimeSpan.FromMilliseconds(500))));

        // ── Properties ──

        public double Value
        {
            get => (double)GetValue(ValueProperty);
            set => SetValue(ValueProperty, value);
        }

        public double Minimum
        {
            get => (double)GetValue(MinimumProperty);
            set => SetValue(MinimumProperty, value);
        }

        public double Maximum
        {
            get => (double)GetValue(MaximumProperty);
            set => SetValue(MaximumProperty, value);
        }

        public Brush GaugeColor
        {
            get => (Brush)GetValue(GaugeColorProperty);
            set => SetValue(GaugeColorProperty, value);
        }

        public Brush TrackColor
        {
            get => (Brush)GetValue(TrackColorProperty);
            set => SetValue(TrackColorProperty, value);
        }

        public GaugeDisplayMode GaugeMode
        {
            get => (GaugeDisplayMode)GetValue(GaugeModeProperty);
            set => SetValue(GaugeModeProperty, value);
        }

        public string Label
        {
            get => (string)GetValue(LabelProperty);
            set => SetValue(LabelProperty, value);
        }

        public bool ShowPercentage
        {
            get => (bool)GetValue(ShowPercentageProperty);
            set => SetValue(ShowPercentageProperty, value);
        }

        public double StrokeThickness
        {
            get => (double)GetValue(StrokeThicknessProperty);
            set => SetValue(StrokeThicknessProperty, value);
        }

        public Duration AnimateDuration
        {
            get => (Duration)GetValue(AnimateDurationProperty);
            set => SetValue(AnimateDurationProperty, value);
        }

        // ── Computed ──

        public double Percentage =>
            Maximum > Minimum ? Math.Clamp((Value - Minimum) / (Maximum - Minimum) * 100, 0, 100) : 0;

        private static void OnValueChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is NeonGauge gauge)
                gauge.InvalidateVisual();
        }

        // ── Rendering ──

        protected override void OnRender(DrawingContext dc)
        {
            base.OnRender(dc);

            if (GaugeMode == GaugeDisplayMode.Bar)
                RenderBar(dc);
            else
                RenderCircular(dc);
        }

        private void RenderCircular(DrawingContext dc)
        {
            double size = Math.Min(ActualWidth, ActualHeight);
            if (size <= 0) return;

            double radius = (size - StrokeThickness) / 2;
            var center = new Point(ActualWidth / 2, ActualHeight / 2);

            // Track arc (full circle)
            var trackPen = new Pen(TrackColor, StrokeThickness) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round };
            dc.DrawEllipse(null, trackPen, center, radius, radius);

            // Value arc
            double pct = Percentage / 100.0;
            if (pct <= 0) return;

            double angle = pct * 360;
            var gaugePen = new Pen(GaugeColor, StrokeThickness) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round };

            double startAngle = -90; // 12 o'clock
            double endAngle = startAngle + angle;

            var startRad = startAngle * Math.PI / 180;
            var endRad = endAngle * Math.PI / 180;

            var startPoint = new Point(
                center.X + radius * Math.Cos(startRad),
                center.Y + radius * Math.Sin(startRad));
            var endPoint = new Point(
                center.X + radius * Math.Cos(endRad),
                center.Y + radius * Math.Sin(endRad));

            var fig = new PathFigure { StartPoint = startPoint, IsClosed = false };
            fig.Segments.Add(new ArcSegment(endPoint, new Size(radius, radius), 0,
                angle > 180, SweepDirection.Clockwise, true));

            var geo = new PathGeometry();
            geo.Figures.Add(fig);
            dc.DrawGeometry(null, gaugePen, geo);

            // Center text
            if (ShowPercentage)
            {
                var text = new FormattedText(
                    $"{Percentage:F0}%",
                    System.Globalization.CultureInfo.CurrentCulture,
                    FlowDirection.LeftToRight,
                    new Typeface(new FontFamily("Segoe UI"), FontStyles.Normal, FontWeights.Bold, FontStretches.Normal),
                    size * 0.18,
                    GaugeColor,
                    VisualTreeHelper.GetDpi(this).PixelsPerDip);
                dc.DrawText(text, new Point(center.X - text.Width / 2, center.Y - text.Height / 2));
            }
        }

        private void RenderBar(DrawingContext dc)
        {
            double w = ActualWidth;
            double h = ActualHeight;
            if (w <= 0 || h <= 0) return;

            double barHeight = Math.Min(h, StrokeThickness * 2);
            double barY = (h - barHeight) / 2;

            // Track
            dc.DrawRoundedRectangle(TrackColor, null,
                new Rect(0, barY, w, barHeight), barHeight / 2, barHeight / 2);

            // Value
            double fillWidth = w * (Percentage / 100.0);
            if (fillWidth > 0)
            {
                dc.DrawRoundedRectangle(GaugeColor, null,
                    new Rect(0, barY, fillWidth, barHeight), barHeight / 2, barHeight / 2);
            }
        }
    }

    public enum GaugeDisplayMode
    {
        Circular,
        Bar
    }
}
