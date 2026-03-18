using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace HyperSpinToolkit.Services
{
    /// <summary>
    /// Transition style for page navigation animations.
    /// </summary>
    public enum TransitionStyle
    {
        PixelDissolve,
        SlideLeft,
        SlideRight,
        FadeThrough,
        NeonWipe,
    }

    /// <summary>
    /// Manages animated page transitions using the PixelDissolve shader effect
    /// and other transition styles. Integrates with NavigationView page changes.
    /// </summary>
    public sealed class PageTransitionService
    {
        #region Singleton

        private static readonly Lazy<PageTransitionService> _instance =
            new(() => new PageTransitionService());

        public static PageTransitionService Instance => _instance.Value;

        #endregion

        #region Fields

        private Frame? _hostFrame;
        private ContentPresenter? _hostPresenter;
        private TransitionStyle _defaultStyle = TransitionStyle.PixelDissolve;
        private TimeSpan _duration = TimeSpan.FromMilliseconds(400);
        private bool _isTransitioning;

        #endregion

        #region Properties

        /// <summary>Default transition style for page changes.</summary>
        public TransitionStyle DefaultStyle
        {
            get => _defaultStyle;
            set => _defaultStyle = value;
        }

        /// <summary>Transition animation duration.</summary>
        public TimeSpan Duration
        {
            get => _duration;
            set => _duration = value > TimeSpan.Zero ? value : TimeSpan.FromMilliseconds(400);
        }

        /// <summary>Whether a transition is currently playing.</summary>
        public bool IsTransitioning => _isTransitioning;

        #endregion

        #region Initialization

        /// <summary>
        /// Attach to a WPF Frame for page transition interception.
        /// </summary>
        public void AttachToFrame(Frame frame)
        {
            _hostFrame = frame;
        }

        /// <summary>
        /// Attach to a ContentPresenter for content transition animation.
        /// </summary>
        public void AttachToPresenter(ContentPresenter presenter)
        {
            _hostPresenter = presenter;
        }

        #endregion

        #region Public API

        /// <summary>
        /// Play a transition animation on the target element.
        /// </summary>
        public void PlayTransition(UIElement target, TransitionStyle? style = null, Action? onComplete = null)
        {
            if (_isTransitioning || target == null) return;
            _isTransitioning = true;

            var chosenStyle = style ?? _defaultStyle;

            switch (chosenStyle)
            {
                case TransitionStyle.PixelDissolve:
                    AnimatePixelDissolve(target, onComplete);
                    break;
                case TransitionStyle.SlideLeft:
                    AnimateSlide(target, -1, onComplete);
                    break;
                case TransitionStyle.SlideRight:
                    AnimateSlide(target, 1, onComplete);
                    break;
                case TransitionStyle.FadeThrough:
                    AnimateFadeThrough(target, onComplete);
                    break;
                case TransitionStyle.NeonWipe:
                    AnimateNeonWipe(target, onComplete);
                    break;
                default:
                    AnimateFadeThrough(target, onComplete);
                    break;
            }
        }

        /// <summary>
        /// Convenience: fade out current content, swap, fade in new content.
        /// </summary>
        public void TransitionContent(ContentPresenter presenter, object newContent,
            TransitionStyle? style = null)
        {
            if (_isTransitioning) return;
            _isTransitioning = true;

            var chosenStyle = style ?? _defaultStyle;
            var element = presenter as UIElement;
            if (element == null) { _isTransitioning = false; return; }

            // Phase 1: Fade out
            var fadeOut = new DoubleAnimation(1.0, 0.0, new Duration(_duration / 2))
            {
                EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseIn }
            };

            fadeOut.Completed += (_, _) =>
            {
                // Swap content
                presenter.Content = newContent;

                // Phase 2: Fade in
                var fadeIn = new DoubleAnimation(0.0, 1.0, new Duration(_duration / 2))
                {
                    EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut }
                };
                fadeIn.Completed += (_, _) => _isTransitioning = false;
                element.BeginAnimation(UIElement.OpacityProperty, fadeIn);
            };

            element.BeginAnimation(UIElement.OpacityProperty, fadeOut);
        }

        #endregion

        #region Animation Implementations

        private void AnimatePixelDissolve(UIElement target, Action? onComplete)
        {
            // Simulate pixel dissolve with opacity + scale scatter
            var halfDuration = new Duration(_duration / 2);

            // Phase 1: dissolve out
            var fadeOut = new DoubleAnimation(1.0, 0.0, halfDuration)
            {
                EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseIn }
            };

            // Add a subtle scale-down for a "pixel scatter" feel
            var scaleTransform = target.RenderTransform as ScaleTransform;
            if (scaleTransform == null)
            {
                scaleTransform = new ScaleTransform(1.0, 1.0);
                target.RenderTransform = scaleTransform;
                target.RenderTransformOrigin = new Point(0.5, 0.5);
            }

            var scaleOut = new DoubleAnimation(1.0, 0.97, halfDuration)
            {
                EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseIn }
            };

            fadeOut.Completed += (_, _) =>
            {
                // Phase 2: dissolve in
                var fadeIn = new DoubleAnimation(0.0, 1.0, halfDuration)
                {
                    EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut }
                };
                var scaleIn = new DoubleAnimation(1.03, 1.0, halfDuration)
                {
                    EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut }
                };
                fadeIn.Completed += (_, _) =>
                {
                    _isTransitioning = false;
                    onComplete?.Invoke();
                };
                target.BeginAnimation(UIElement.OpacityProperty, fadeIn);
                scaleTransform.BeginAnimation(ScaleTransform.ScaleXProperty, scaleIn);
                scaleTransform.BeginAnimation(ScaleTransform.ScaleYProperty, scaleIn);
            };

            target.BeginAnimation(UIElement.OpacityProperty, fadeOut);
            scaleTransform.BeginAnimation(ScaleTransform.ScaleXProperty, scaleOut);
            scaleTransform.BeginAnimation(ScaleTransform.ScaleYProperty, scaleOut);
        }

        private void AnimateSlide(UIElement target, int direction, Action? onComplete)
        {
            var translate = target.RenderTransform as TranslateTransform;
            if (translate == null)
            {
                translate = new TranslateTransform(0, 0);
                target.RenderTransform = translate;
            }

            double slideDistance = 120 * direction;
            var halfDuration = new Duration(_duration / 2);

            // Slide out
            var slideOut = new DoubleAnimation(0, slideDistance, halfDuration)
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseIn }
            };
            var fadeOut = new DoubleAnimation(1.0, 0.0, halfDuration);

            slideOut.Completed += (_, _) =>
            {
                translate.X = -slideDistance;

                // Slide in
                var slideIn = new DoubleAnimation(-slideDistance, 0, halfDuration)
                {
                    EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut }
                };
                var fadeIn = new DoubleAnimation(0.0, 1.0, halfDuration);
                slideIn.Completed += (_, _) =>
                {
                    _isTransitioning = false;
                    onComplete?.Invoke();
                };
                translate.BeginAnimation(TranslateTransform.XProperty, slideIn);
                target.BeginAnimation(UIElement.OpacityProperty, fadeIn);
            };

            translate.BeginAnimation(TranslateTransform.XProperty, slideOut);
            target.BeginAnimation(UIElement.OpacityProperty, fadeOut);
        }

        private void AnimateFadeThrough(UIElement target, Action? onComplete)
        {
            var halfDuration = new Duration(_duration / 2);

            var fadeOut = new DoubleAnimation(1.0, 0.0, halfDuration)
            {
                EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseIn }
            };
            fadeOut.Completed += (_, _) =>
            {
                var fadeIn = new DoubleAnimation(0.0, 1.0, halfDuration)
                {
                    EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut }
                };
                fadeIn.Completed += (_, _) =>
                {
                    _isTransitioning = false;
                    onComplete?.Invoke();
                };
                target.BeginAnimation(UIElement.OpacityProperty, fadeIn);
            };
            target.BeginAnimation(UIElement.OpacityProperty, fadeOut);
        }

        private void AnimateNeonWipe(UIElement target, Action? onComplete)
        {
            // Neon wipe: clip-based reveal with glow line
            var halfDuration = new Duration(_duration / 2);

            // Use opacity + scale for arcade feel
            var scaleTransform = target.RenderTransform as ScaleTransform;
            if (scaleTransform == null)
            {
                scaleTransform = new ScaleTransform(1.0, 1.0);
                target.RenderTransform = scaleTransform;
                target.RenderTransformOrigin = new Point(0.5, 0.5);
            }

            var fadeOut = new DoubleAnimation(1.0, 0.0, halfDuration);
            var scaleOut = new DoubleAnimation(1.0, 1.05, halfDuration);

            fadeOut.Completed += (_, _) =>
            {
                scaleTransform.ScaleX = 0.95;
                scaleTransform.ScaleY = 0.95;

                var fadeIn = new DoubleAnimation(0.0, 1.0, halfDuration);
                var scaleIn = new DoubleAnimation(0.95, 1.0, halfDuration)
                {
                    EasingFunction = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.3 }
                };
                fadeIn.Completed += (_, _) =>
                {
                    _isTransitioning = false;
                    onComplete?.Invoke();
                };
                target.BeginAnimation(UIElement.OpacityProperty, fadeIn);
                scaleTransform.BeginAnimation(ScaleTransform.ScaleXProperty, scaleIn);
                scaleTransform.BeginAnimation(ScaleTransform.ScaleYProperty, scaleIn);
            };

            target.BeginAnimation(UIElement.OpacityProperty, fadeOut);
            scaleTransform.BeginAnimation(ScaleTransform.ScaleXProperty, scaleOut);
            scaleTransform.BeginAnimation(ScaleTransform.ScaleYProperty, scaleOut);
        }

        #endregion
    }
}
