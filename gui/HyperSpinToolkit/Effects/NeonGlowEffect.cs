using System.Windows.Media;
using System.Windows.Media.Effects;

namespace HyperSpinToolkit.Effects
{
    /// <summary>
    /// M46 — Neon Glow Effect: Bloom/glow shader for buttons, text, active elements.
    /// Factory that creates DropShadowEffect instances with neon-optimized presets.
    /// </summary>
    public static class NeonGlowEffect
    {
        public static DropShadowEffect Create(Color color, double blurRadius = 16, double intensity = 0.8)
        {
            return new DropShadowEffect
            {
                ShadowDepth = 0,
                BlurRadius = blurRadius,
                Opacity = intensity,
                Color = color
            };
        }

        // ── Factory presets ──

        public static DropShadowEffect Blue(double intensity = 0.8) =>
            Create(Color.FromRgb(0x00, 0xD4, 0xFF), 16, intensity);

        public static DropShadowEffect Pink(double intensity = 0.8) =>
            Create(Color.FromRgb(0xFF, 0x00, 0x88), 16, intensity);

        public static DropShadowEffect Green(double intensity = 0.8) =>
            Create(Color.FromRgb(0x39, 0xFF, 0x14), 16, intensity);

        public static DropShadowEffect Yellow(double intensity = 0.8) =>
            Create(Color.FromRgb(0xFF, 0xF0, 0x00), 16, intensity);

        public static DropShadowEffect Purple(double intensity = 0.8) =>
            Create(Color.FromRgb(0xBF, 0x00, 0xFF), 16, intensity);
    }
}
