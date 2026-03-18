using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Effects;

namespace HyperSpinToolkit.Effects
{
    /// <summary>
    /// M46 — Neon Glow Effect: Bloom/glow shader for buttons, text, active elements.
    /// Wraps DropShadowEffect with neon-optimized defaults and color presets.
    /// </summary>
    public class NeonGlowEffect : DropShadowEffect
    {
        public static readonly DependencyProperty GlowColorProperty =
            DependencyProperty.Register(nameof(GlowColor), typeof(Color), typeof(NeonGlowEffect),
                new UIPropertyMetadata(Color.FromRgb(0x00, 0xD4, 0xFF), OnGlowColorChanged));

        public static readonly DependencyProperty GlowIntensityProperty =
            DependencyProperty.Register(nameof(GlowIntensity), typeof(double), typeof(NeonGlowEffect),
                new UIPropertyMetadata(0.8));

        public static readonly DependencyProperty GlowRadiusProperty =
            DependencyProperty.Register(nameof(GlowRadius), typeof(double), typeof(NeonGlowEffect),
                new UIPropertyMetadata(16.0));

        public Color GlowColor
        {
            get => (Color)GetValue(GlowColorProperty);
            set => SetValue(GlowColorProperty, value);
        }

        public double GlowIntensity
        {
            get => (double)GetValue(GlowIntensityProperty);
            set => SetValue(GlowIntensityProperty, value);
        }

        public double GlowRadius
        {
            get => (double)GetValue(GlowRadiusProperty);
            set => SetValue(GlowRadiusProperty, value);
        }

        public NeonGlowEffect()
        {
            ShadowDepth = 0;
            BlurRadius = 16;
            Opacity = 0.8;
            Color = Color.FromRgb(0x00, 0xD4, 0xFF);
        }

        private static void OnGlowColorChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is NeonGlowEffect effect)
            {
                effect.Color = (Color)e.NewValue;
            }
        }

        // ── Factory presets ──

        public static NeonGlowEffect Blue(double intensity = 0.8) => new()
        {
            GlowColor = Color.FromRgb(0x00, 0xD4, 0xFF),
            Color = Color.FromRgb(0x00, 0xD4, 0xFF),
            BlurRadius = 16,
            Opacity = intensity
        };

        public static NeonGlowEffect Pink(double intensity = 0.8) => new()
        {
            GlowColor = Color.FromRgb(0xFF, 0x00, 0x88),
            Color = Color.FromRgb(0xFF, 0x00, 0x88),
            BlurRadius = 16,
            Opacity = intensity
        };

        public static NeonGlowEffect Green(double intensity = 0.8) => new()
        {
            GlowColor = Color.FromRgb(0x39, 0xFF, 0x14),
            Color = Color.FromRgb(0x39, 0xFF, 0x14),
            BlurRadius = 16,
            Opacity = intensity
        };

        public static NeonGlowEffect Yellow(double intensity = 0.8) => new()
        {
            GlowColor = Color.FromRgb(0xFF, 0xF0, 0x00),
            Color = Color.FromRgb(0xFF, 0xF0, 0x00),
            BlurRadius = 16,
            Opacity = intensity
        };

        public static NeonGlowEffect Purple(double intensity = 0.8) => new()
        {
            GlowColor = Color.FromRgb(0xBF, 0x00, 0xFF),
            Color = Color.FromRgb(0xBF, 0x00, 0xFF),
            BlurRadius = 16,
            Opacity = intensity
        };
    }
}
