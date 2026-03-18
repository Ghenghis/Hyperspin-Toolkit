using System;
using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;

namespace HyperSpinToolkit.Controls
{
    /// <summary>
    /// M45 — CrtTerminal: Retro scanline text terminal control for agent console output.
    /// Supports auto-scroll, blinking cursor, command history, and scanline overlay.
    /// </summary>
    public class CrtTerminal : Control
    {
        private readonly ObservableCollection<TerminalLine> _lines = new();
        private int _cursorBlink;
        private DispatcherTimer? _blinkTimer;

        static CrtTerminal()
        {
            DefaultStyleKeyProperty.OverrideMetadata(typeof(CrtTerminal),
                new FrameworkPropertyMetadata(typeof(CrtTerminal)));
        }

        public CrtTerminal()
        {
            _blinkTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(530) };
            _blinkTimer.Tick += (_, _) => { _cursorBlink = 1 - _cursorBlink; InvalidateVisual(); };
            Loaded += (_, _) => _blinkTimer.Start();
            Unloaded += (_, _) => _blinkTimer?.Stop();
        }

        // ── Dependency Properties ──

        public static readonly DependencyProperty MaxLinesProperty =
            DependencyProperty.Register(nameof(MaxLines), typeof(int), typeof(CrtTerminal),
                new PropertyMetadata(500));

        public static readonly DependencyProperty PromptProperty =
            DependencyProperty.Register(nameof(Prompt), typeof(string), typeof(CrtTerminal),
                new PropertyMetadata("λ "));

        public static readonly DependencyProperty TextColorProperty =
            DependencyProperty.Register(nameof(TextColor), typeof(Brush), typeof(CrtTerminal),
                new PropertyMetadata(new SolidColorBrush(Color.FromRgb(0x39, 0xFF, 0x14))));

        public static readonly DependencyProperty ShowScanLinesProperty =
            DependencyProperty.Register(nameof(ShowScanLines), typeof(bool), typeof(CrtTerminal),
                new PropertyMetadata(true));

        public static readonly DependencyProperty FontSizeTerminalProperty =
            DependencyProperty.Register(nameof(FontSizeTerminal), typeof(double), typeof(CrtTerminal),
                new PropertyMetadata(13.0));

        public int MaxLines
        {
            get => (int)GetValue(MaxLinesProperty);
            set => SetValue(MaxLinesProperty, value);
        }

        public string Prompt
        {
            get => (string)GetValue(PromptProperty);
            set => SetValue(PromptProperty, value);
        }

        public Brush TextColor
        {
            get => (Brush)GetValue(TextColorProperty);
            set => SetValue(TextColorProperty, value);
        }

        public bool ShowScanLines
        {
            get => (bool)GetValue(ShowScanLinesProperty);
            set => SetValue(ShowScanLinesProperty, value);
        }

        public double FontSizeTerminal
        {
            get => (double)GetValue(FontSizeTerminalProperty);
            set => SetValue(FontSizeTerminalProperty, value);
        }

        // ── Public API ──

        public void WriteLine(string text, TerminalLineType type = TerminalLineType.Output)
        {
            _lines.Add(new TerminalLine(text, type));
            while (_lines.Count > MaxLines)
                _lines.RemoveAt(0);
            InvalidateVisual();
        }

        public void WriteCommand(string command)
        {
            WriteLine($"{Prompt}{command}", TerminalLineType.Command);
        }

        public void WriteError(string error)
        {
            WriteLine($"ERROR: {error}", TerminalLineType.Error);
        }

        public void WriteSystem(string msg)
        {
            WriteLine(msg, TerminalLineType.System);
        }

        public void Clear()
        {
            _lines.Clear();
            InvalidateVisual();
        }

        // ── Rendering ──

        protected override void OnRender(DrawingContext dc)
        {
            base.OnRender(dc);

            // Background
            dc.DrawRectangle(new SolidColorBrush(Color.FromRgb(0x08, 0x08, 0x10)), null,
                new Rect(0, 0, ActualWidth, ActualHeight));

            var typeface = new Typeface(
                new FontFamily("JetBrains Mono, Cascadia Code, Consolas"),
                FontStyles.Normal, FontWeights.Normal, FontStretches.Normal);

            double lineHeight = FontSizeTerminal + 4;
            double y = ActualHeight - lineHeight; // Start from bottom
            double ppd = VisualTreeHelper.GetDpi(this).PixelsPerDip;

            // Render lines bottom-up (newest at bottom)
            int startIdx = Math.Max(0, _lines.Count - (int)(ActualHeight / lineHeight));
            for (int i = _lines.Count - 1; i >= startIdx && y >= -lineHeight; i--)
            {
                var line = _lines[i];
                Brush color = line.Type switch
                {
                    TerminalLineType.Command => TextColor,
                    TerminalLineType.Error => new SolidColorBrush(Color.FromRgb(0xFF, 0x17, 0x44)),
                    TerminalLineType.System => new SolidColorBrush(Color.FromRgb(0x00, 0xD4, 0xFF)),
                    _ => TextColor,
                };

                if (line.Type == TerminalLineType.Output)
                    color = new SolidColorBrush(Color.FromArgb(0xCC, 0x39, 0xFF, 0x14));

                var ft = new FormattedText(line.Text, System.Globalization.CultureInfo.CurrentCulture,
                    FlowDirection.LeftToRight, typeface, FontSizeTerminal, color, ppd)
                {
                    MaxTextWidth = Math.Max(1, ActualWidth - 16)
                };

                dc.DrawText(ft, new Point(8, y));
                y -= lineHeight;
            }

            // Blinking cursor at bottom
            if (_cursorBlink == 1)
            {
                var cursorBrush = TextColor;
                dc.DrawRectangle(cursorBrush, null,
                    new Rect(8, ActualHeight - lineHeight + 2, FontSizeTerminal * 0.6, FontSizeTerminal));
            }

            // Scanline overlay
            if (ShowScanLines)
            {
                var scanBrush = new SolidColorBrush(Color.FromArgb(0x10, 0x00, 0x00, 0x00));
                for (double sy = 0; sy < ActualHeight; sy += 3)
                {
                    dc.DrawRectangle(scanBrush, null, new Rect(0, sy, ActualWidth, 1));
                }
            }
        }
    }

    public class TerminalLine
    {
        public string Text { get; }
        public TerminalLineType Type { get; }
        public DateTime Timestamp { get; }

        public TerminalLine(string text, TerminalLineType type)
        {
            Text = text;
            Type = type;
            Timestamp = DateTime.Now;
        }
    }

    public enum TerminalLineType
    {
        Output,
        Command,
        Error,
        System
    }
}
