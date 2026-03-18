using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;

namespace HyperSpinToolkit.Effects
{
    /// <summary>
    /// M46 — Particle System: Custom WPF particle engine with spark, glow, and pixel sprites.
    /// Presets: ambient stars, neon rain, arcade sparks, fire pixels.
    /// </summary>
    public class ParticleCanvas : Canvas
    {
        private readonly List<Particle> _particles = new();
        private readonly Random _rng = new();
        private DispatcherTimer? _timer;
        private DateTime _lastTick;

        public static readonly DependencyProperty PresetProperty =
            DependencyProperty.Register(nameof(Preset), typeof(ParticlePreset), typeof(ParticleCanvas),
                new PropertyMetadata(ParticlePreset.AmbientStars, OnPresetChanged));

        public static readonly DependencyProperty MaxParticlesProperty =
            DependencyProperty.Register(nameof(MaxParticles), typeof(int), typeof(ParticleCanvas),
                new PropertyMetadata(80));

        public static readonly DependencyProperty SpawnRateProperty =
            DependencyProperty.Register(nameof(SpawnRate), typeof(double), typeof(ParticleCanvas),
                new PropertyMetadata(2.0));

        public static readonly DependencyProperty IsActiveProperty =
            DependencyProperty.Register(nameof(IsActive), typeof(bool), typeof(ParticleCanvas),
                new PropertyMetadata(true, OnIsActiveChanged));

        public ParticlePreset Preset
        {
            get => (ParticlePreset)GetValue(PresetProperty);
            set => SetValue(PresetProperty, value);
        }

        public int MaxParticles
        {
            get => (int)GetValue(MaxParticlesProperty);
            set => SetValue(MaxParticlesProperty, value);
        }

        public double SpawnRate
        {
            get => (double)GetValue(SpawnRateProperty);
            set => SetValue(SpawnRateProperty, value);
        }

        public bool IsActive
        {
            get => (bool)GetValue(IsActiveProperty);
            set => SetValue(IsActiveProperty, value);
        }

        public ParticleCanvas()
        {
            IsHitTestVisible = false;
            ClipToBounds = true;
            Background = Brushes.Transparent;
            Loaded += (_, _) => Start();
            Unloaded += (_, _) => Stop();
        }

        public void Start()
        {
            if (_timer != null) return;
            _lastTick = DateTime.Now;
            _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(33) }; // ~30fps
            _timer.Tick += OnTick;
            _timer.Start();
        }

        public void Stop()
        {
            _timer?.Stop();
            _timer = null;
        }

        private void OnTick(object? sender, EventArgs e)
        {
            if (!IsActive) return;
            var now = DateTime.Now;
            double dt = (now - _lastTick).TotalSeconds;
            _lastTick = now;

            double w = ActualWidth, h = ActualHeight;
            if (w <= 0 || h <= 0) return;

            // Spawn new particles
            int toSpawn = (int)(SpawnRate * dt * 60);
            for (int i = 0; i < toSpawn && _particles.Count < MaxParticles; i++)
                _particles.Add(CreateParticle(w, h));

            // Update & remove dead
            _particles.RemoveAll(p =>
            {
                p.Age += dt;
                p.X += p.Vx * dt;
                p.Y += p.Vy * dt;
                p.Opacity = Math.Max(0, 1.0 - p.Age / p.Lifetime);

                // Apply gravity for sparks
                if (Preset == ParticlePreset.ArcadeSparks || Preset == ParticlePreset.FirePixels)
                    p.Vy += 40 * dt;

                return p.Age >= p.Lifetime || p.Y > h + 10 || p.Y < -10 || p.X < -10 || p.X > w + 10;
            });

            InvalidateVisual();
        }

        private Particle CreateParticle(double w, double h)
        {
            return Preset switch
            {
                ParticlePreset.AmbientStars => new Particle
                {
                    X = _rng.NextDouble() * w,
                    Y = _rng.NextDouble() * h,
                    Vx = (_rng.NextDouble() - 0.5) * 5,
                    Vy = (_rng.NextDouble() - 0.5) * 5,
                    Size = 1 + _rng.NextDouble() * 2,
                    Color = Color.FromArgb(0xCC, 0xE0, 0xE0, 0xFF),
                    Lifetime = 3 + _rng.NextDouble() * 5,
                },
                ParticlePreset.NeonRain => new Particle
                {
                    X = _rng.NextDouble() * w,
                    Y = -5,
                    Vx = 0,
                    Vy = 60 + _rng.NextDouble() * 120,
                    Size = 1 + _rng.NextDouble() * 1.5,
                    Color = PickNeonColor(),
                    Lifetime = h / 80 + _rng.NextDouble() * 2,
                },
                ParticlePreset.ArcadeSparks => new Particle
                {
                    X = w / 2 + (_rng.NextDouble() - 0.5) * w * 0.6,
                    Y = h * 0.8,
                    Vx = (_rng.NextDouble() - 0.5) * 100,
                    Vy = -80 - _rng.NextDouble() * 120,
                    Size = 2 + _rng.NextDouble() * 3,
                    Color = Color.FromRgb(0xFF, 0xF0, 0x00),
                    Lifetime = 0.5 + _rng.NextDouble() * 1.5,
                },
                ParticlePreset.FirePixels => new Particle
                {
                    X = _rng.NextDouble() * w,
                    Y = h + 5,
                    Vx = (_rng.NextDouble() - 0.5) * 20,
                    Vy = -30 - _rng.NextDouble() * 60,
                    Size = 2 + _rng.NextDouble() * 4,
                    Color = _rng.NextDouble() > 0.5
                        ? Color.FromRgb(0xFF, 0x6E, 0x00)
                        : Color.FromRgb(0xFF, 0x17, 0x44),
                    Lifetime = 1 + _rng.NextDouble() * 2,
                },
                _ => new Particle
                {
                    X = _rng.NextDouble() * w,
                    Y = _rng.NextDouble() * h,
                    Size = 2,
                    Color = Colors.White,
                    Lifetime = 2,
                }
            };
        }

        private Color PickNeonColor()
        {
            return _rng.Next(5) switch
            {
                0 => Color.FromRgb(0x00, 0xD4, 0xFF),
                1 => Color.FromRgb(0xFF, 0x00, 0x88),
                2 => Color.FromRgb(0x39, 0xFF, 0x14),
                3 => Color.FromRgb(0xBF, 0x00, 0xFF),
                _ => Color.FromRgb(0x00, 0xFF, 0xCC),
            };
        }

        protected override void OnRender(DrawingContext dc)
        {
            base.OnRender(dc);
            foreach (var p in _particles)
            {
                var color = Color.FromArgb(
                    (byte)(p.Color.A * Math.Clamp(p.Opacity, 0, 1)),
                    p.Color.R, p.Color.G, p.Color.B);
                var brush = new SolidColorBrush(color);

                if (Preset == ParticlePreset.FirePixels || Preset == ParticlePreset.ArcadeSparks)
                {
                    // Square pixel particles
                    dc.DrawRectangle(brush, null, new Rect(p.X - p.Size / 2, p.Y - p.Size / 2, p.Size, p.Size));
                }
                else
                {
                    // Round glow particles
                    dc.DrawEllipse(brush, null, new Point(p.X, p.Y), p.Size, p.Size);
                }
            }
        }

        private static void OnPresetChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is ParticleCanvas canvas)
                canvas._particles.Clear();
        }

        private static void OnIsActiveChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is ParticleCanvas canvas)
            {
                if ((bool)e.NewValue)
                    canvas.Start();
                else
                    canvas.Stop();
            }
        }
    }

    public class Particle
    {
        public double X { get; set; }
        public double Y { get; set; }
        public double Vx { get; set; }
        public double Vy { get; set; }
        public double Size { get; set; }
        public Color Color { get; set; }
        public double Lifetime { get; set; }
        public double Age { get; set; }
        public double Opacity { get; set; } = 1.0;
    }

    public enum ParticlePreset
    {
        AmbientStars,
        NeonRain,
        ArcadeSparks,
        FirePixels
    }
}
