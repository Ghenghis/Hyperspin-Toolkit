using System;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Effects;

namespace HyperSpinToolkit.Effects
{
    /// <summary>
    /// M46 — CRT Scanline Effect: Retro CRT monitor look with scanlines,
    /// slight curvature distortion, and phosphor glow simulation.
    /// Falls back to software rendering if HLSL shaders aren't available.
    /// </summary>
    public class CrtScanlineEffect : ShaderEffect
    {
        // Scanline intensity (0 = off, 1 = heavy)
        public static readonly DependencyProperty IntensityProperty =
            DependencyProperty.Register(nameof(Intensity), typeof(double), typeof(CrtScanlineEffect),
                new UIPropertyMetadata(0.3, PixelShaderConstantCallback(0)));

        // Scanline spacing in pixels
        public static readonly DependencyProperty LineSpacingProperty =
            DependencyProperty.Register(nameof(LineSpacing), typeof(double), typeof(CrtScanlineEffect),
                new UIPropertyMetadata(3.0, PixelShaderConstantCallback(1)));

        // Curvature amount (0 = flat, 1 = heavy barrel distortion)
        public static readonly DependencyProperty CurvatureProperty =
            DependencyProperty.Register(nameof(Curvature), typeof(double), typeof(CrtScanlineEffect),
                new UIPropertyMetadata(0.0, PixelShaderConstantCallback(2)));

        // Phosphor brightness boost
        public static readonly DependencyProperty BrightnessProperty =
            DependencyProperty.Register(nameof(Brightness), typeof(double), typeof(CrtScanlineEffect),
                new UIPropertyMetadata(1.05, PixelShaderConstantCallback(3)));

        public double Intensity
        {
            get => (double)GetValue(IntensityProperty);
            set => SetValue(IntensityProperty, value);
        }

        public double LineSpacing
        {
            get => (double)GetValue(LineSpacingProperty);
            set => SetValue(LineSpacingProperty, value);
        }

        public double Curvature
        {
            get => (double)GetValue(CurvatureProperty);
            set => SetValue(CurvatureProperty, value);
        }

        public double Brightness
        {
            get => (double)GetValue(BrightnessProperty);
            set => SetValue(BrightnessProperty, value);
        }

        public CrtScanlineEffect()
        {
            // HLSL shader would be loaded here:
            // PixelShader = new PixelShader { UriSource = new Uri("pack://application:,,,/Effects/CrtScanline.ps") };
            // For now, we use the software fallback via OnRender in consuming controls
            UpdateShaderValue(IntensityProperty);
            UpdateShaderValue(LineSpacingProperty);
            UpdateShaderValue(CurvatureProperty);
            UpdateShaderValue(BrightnessProperty);
        }
    }
}
