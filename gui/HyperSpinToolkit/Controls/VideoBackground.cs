using System;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;

namespace HyperSpinToolkit.Controls
{
    /// <summary>
    /// M47 — VideoBackground: Seamless loop of game preview videos from the 47K video library.
    /// Uses WPF MediaElement with fallback to static image. Supports random selection
    /// per page from asset index (M41). LibVLCSharp upgrade path available.
    /// </summary>
    public class VideoBackground : Decorator
    {
        private MediaElement? _media;
        private Image? _fallbackImage;
        private bool _isPlaying;

        public static readonly DependencyProperty VideoSourceProperty =
            DependencyProperty.Register(nameof(VideoSource), typeof(string), typeof(VideoBackground),
                new PropertyMetadata("", OnVideoSourceChanged));

        public static readonly DependencyProperty VolumeProperty =
            DependencyProperty.Register(nameof(Volume), typeof(double), typeof(VideoBackground),
                new PropertyMetadata(0.0)); // Default muted for background

        public static readonly DependencyProperty IsLoopingProperty =
            DependencyProperty.Register(nameof(IsLooping), typeof(bool), typeof(VideoBackground),
                new PropertyMetadata(true));

        public static readonly DependencyProperty OpacityOverlayProperty =
            DependencyProperty.Register(nameof(OpacityOverlay), typeof(double), typeof(VideoBackground),
                new PropertyMetadata(0.3)); // Dim overlay so content is readable

        public static readonly DependencyProperty FallbackImageSourceProperty =
            DependencyProperty.Register(nameof(FallbackImageSource), typeof(string), typeof(VideoBackground),
                new PropertyMetadata(""));

        public static readonly DependencyProperty IsVideoEnabledProperty =
            DependencyProperty.Register(nameof(IsVideoEnabled), typeof(bool), typeof(VideoBackground),
                new PropertyMetadata(true, OnIsVideoEnabledChanged));

        public string VideoSource
        {
            get => (string)GetValue(VideoSourceProperty);
            set => SetValue(VideoSourceProperty, value);
        }

        public double Volume
        {
            get => (double)GetValue(VolumeProperty);
            set => SetValue(VolumeProperty, value);
        }

        public bool IsLooping
        {
            get => (bool)GetValue(IsLoopingProperty);
            set => SetValue(IsLoopingProperty, value);
        }

        public double OpacityOverlay
        {
            get => (double)GetValue(OpacityOverlayProperty);
            set => SetValue(OpacityOverlayProperty, value);
        }

        public string FallbackImageSource
        {
            get => (string)GetValue(FallbackImageSourceProperty);
            set => SetValue(FallbackImageSourceProperty, value);
        }

        public bool IsVideoEnabled
        {
            get => (bool)GetValue(IsVideoEnabledProperty);
            set => SetValue(IsVideoEnabledProperty, value);
        }

        public VideoBackground()
        {
            Loaded += OnLoaded;
            Unloaded += OnUnloaded;
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            if (!string.IsNullOrEmpty(VideoSource) && IsVideoEnabled)
                PlayVideo(VideoSource);
        }

        private void OnUnloaded(object sender, RoutedEventArgs e)
        {
            StopVideo();
        }

        public void PlayVideo(string path)
        {
            if (!File.Exists(path))
            {
                ShowFallback();
                return;
            }

            try
            {
                StopVideo();

                _media = new MediaElement
                {
                    LoadedBehavior = MediaState.Manual,
                    UnloadedBehavior = MediaState.Close,
                    Stretch = Stretch.UniformToFill,
                    Volume = Volume,
                    IsMuted = Volume <= 0,
                    Opacity = 1.0 - OpacityOverlay,
                };

                _media.MediaEnded += (_, _) =>
                {
                    if (IsLooping && _media != null)
                    {
                        _media.Position = TimeSpan.Zero;
                        _media.Play();
                    }
                };

                _media.MediaFailed += (_, args) =>
                {
                    System.Diagnostics.Debug.WriteLine($"Video failed: {args.ErrorException?.Message}");
                    ShowFallback();
                };

                _media.Source = new Uri(path, UriKind.Absolute);
                Child = _media;
                _media.Play();
                _isPlaying = true;
            }
            catch
            {
                ShowFallback();
            }
        }

        public void StopVideo()
        {
            if (_media != null)
            {
                try { _media.Stop(); _media.Close(); } catch { }
                _media = null;
            }
            _isPlaying = false;
        }

        public void PauseVideo()
        {
            _media?.Pause();
            _isPlaying = false;
        }

        public void ResumeVideo()
        {
            if (_media != null && !_isPlaying)
            {
                _media.Play();
                _isPlaying = true;
            }
        }

        private void ShowFallback()
        {
            StopVideo();
            if (!string.IsNullOrEmpty(FallbackImageSource) && File.Exists(FallbackImageSource))
            {
                try
                {
                    var bi = new System.Windows.Media.Imaging.BitmapImage();
                    bi.BeginInit();
                    bi.UriSource = new Uri(FallbackImageSource, UriKind.Absolute);
                    bi.CacheOption = System.Windows.Media.Imaging.BitmapCacheOption.OnLoad;
                    bi.EndInit();

                    _fallbackImage = new Image
                    {
                        Source = bi,
                        Stretch = Stretch.UniformToFill,
                        Opacity = 1.0 - OpacityOverlay,
                    };
                    Child = _fallbackImage;
                }
                catch { }
            }
        }

        private static void OnVideoSourceChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is VideoBackground vb && vb.IsLoaded && vb.IsVideoEnabled)
                vb.PlayVideo((string)e.NewValue);
        }

        private static void OnIsVideoEnabledChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is VideoBackground vb)
            {
                if (!(bool)e.NewValue)
                    vb.StopVideo();
                else if (!string.IsNullOrEmpty(vb.VideoSource))
                    vb.PlayVideo(vb.VideoSource);
            }
        }
    }
}
