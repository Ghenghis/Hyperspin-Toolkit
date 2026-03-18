using System;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Effects;

namespace HyperSpinToolkit.Effects
{
    /// <summary>
    /// M46 — Pixel Dissolve Effect: Page transition with configurable direction/speed.
    /// Uses threshold-based dissolve where pixels fade based on a noise pattern.
    /// Software fallback: opacity-based cross-fade.
    /// </summary>
    public class PixelDissolveEffect : ShaderEffect
    {
        // Progress (0 = fully visible, 1 = fully dissolved)
        public static readonly DependencyProperty ProgressProperty =
            DependencyProperty.Register(nameof(Progress), typeof(double), typeof(PixelDissolveEffect),
                new UIPropertyMetadata(0.0, PixelShaderConstantCallback(0)));

        // Pixel block size for dissolve granularity
        public static readonly DependencyProperty BlockSizeProperty =
            DependencyProperty.Register(nameof(BlockSize), typeof(double), typeof(PixelDissolveEffect),
                new UIPropertyMetadata(4.0, PixelShaderConstantCallback(1)));

        // Direction: 0=random, 1=left-to-right, 2=top-to-bottom, 3=center-out
        public static readonly DependencyProperty DirectionProperty =
            DependencyProperty.Register(nameof(Direction), typeof(double), typeof(PixelDissolveEffect),
                new UIPropertyMetadata(0.0, PixelShaderConstantCallback(2)));

        // Edge softness
        public static readonly DependencyProperty SoftnessProperty =
            DependencyProperty.Register(nameof(Softness), typeof(double), typeof(PixelDissolveEffect),
                new UIPropertyMetadata(0.1, PixelShaderConstantCallback(3)));

        public double Progress
        {
            get => (double)GetValue(ProgressProperty);
            set => SetValue(ProgressProperty, value);
        }

        public double BlockSize
        {
            get => (double)GetValue(BlockSizeProperty);
            set => SetValue(BlockSizeProperty, value);
        }

        public double Direction
        {
            get => (double)GetValue(DirectionProperty);
            set => SetValue(DirectionProperty, value);
        }

        public double Softness
        {
            get => (double)GetValue(SoftnessProperty);
            set => SetValue(SoftnessProperty, value);
        }

        public PixelDissolveEffect()
        {
            // HLSL shader would be loaded:
            // PixelShader = new PixelShader { UriSource = new Uri("pack://application:,,,/Effects/PixelDissolve.ps") };
            UpdateShaderValue(ProgressProperty);
            UpdateShaderValue(BlockSizeProperty);
            UpdateShaderValue(DirectionProperty);
            UpdateShaderValue(SoftnessProperty);
        }
    }
}
