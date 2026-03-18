using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace HyperSpinToolkit.Services
{
    /// <summary>
    /// Performance statistics snapshot for monitoring.
    /// </summary>
    public class PerformanceStats
    {
        public long WorkingSetMB { get; set; }
        public long GcTotalMemoryMB { get; set; }
        public int CachedThumbnails { get; set; }
        public int CachedImages { get; set; }
        public int ActiveVideoPlayers { get; set; }
        public double FrameRate { get; set; }
        public TimeSpan Uptime { get; set; }
    }

    /// <summary>
    /// Centralized resource manager for the arcade GUI. Handles:
    /// - Thumbnail caching with LRU eviction
    /// - Lazy video loading / disposal on page leave
    /// - Asset preloading for adjacent pages
    /// - Memory pressure monitoring and cleanup
    /// - Frame rate tracking
    /// </summary>
    public sealed class ResourceManager : IDisposable
    {
        #region Singleton

        private static readonly Lazy<ResourceManager> _instance =
            new(() => new ResourceManager());

        public static ResourceManager Instance => _instance.Value;

        #endregion

        #region Fields

        private readonly ConcurrentDictionary<string, WeakReference<BitmapSource>> _thumbnailCache = new();
        private readonly ConcurrentDictionary<string, BitmapSource> _pinnedCache = new();
        private readonly ConcurrentQueue<string> _lruOrder = new();
        private readonly HashSet<IDisposable> _activeVideoPlayers = new();
        private readonly DispatcherTimer _memoryMonitor;
        private readonly DateTime _startTime = DateTime.UtcNow;
        private bool _disposed;

        // Configuration
        private const int MAX_THUMBNAIL_CACHE = 500;
        private const int MAX_PINNED_CACHE = 50;
        private const long MEMORY_PRESSURE_THRESHOLD_MB = 800;
        private const int THUMBNAIL_DECODE_WIDTH = 200;

        // Frame rate tracking
        private int _frameCount;
        private DateTime _lastFpsSample = DateTime.UtcNow;
        private double _currentFps;

        #endregion

        #region Properties

        /// <summary>Current estimated frame rate.</summary>
        public double CurrentFps => _currentFps;

        /// <summary>Number of cached thumbnails.</summary>
        public int CachedThumbnailCount => _thumbnailCache.Count;

        /// <summary>Number of pinned (never evicted) images.</summary>
        public int PinnedImageCount => _pinnedCache.Count;

        /// <summary>Application uptime.</summary>
        public TimeSpan Uptime => DateTime.UtcNow - _startTime;

        #endregion

        #region Constructor

        private ResourceManager()
        {
            _memoryMonitor = new DispatcherTimer
            {
                Interval = TimeSpan.FromSeconds(10)
            };
            _memoryMonitor.Tick += OnMemoryCheck;
            _memoryMonitor.Start();

            // Hook into WPF rendering for FPS tracking
            CompositionTarget.Rendering += OnRendering;
        }

        #endregion

        #region Thumbnail Cache

        /// <summary>
        /// Get or load a thumbnail from cache. Returns null if file doesn't exist.
        /// Thumbnails are decoded at reduced resolution for memory efficiency.
        /// </summary>
        public BitmapSource? GetThumbnail(string filePath)
        {
            if (string.IsNullOrEmpty(filePath))
                return null;

            string key = filePath.ToLowerInvariant();

            // Check pinned cache first
            if (_pinnedCache.TryGetValue(key, out var pinned))
                return pinned;

            // Check weak reference cache
            if (_thumbnailCache.TryGetValue(key, out var weakRef) && weakRef.TryGetTarget(out var cached))
                return cached;

            // Load and cache
            var thumbnail = LoadThumbnail(filePath);
            if (thumbnail != null)
            {
                _thumbnailCache[key] = new WeakReference<BitmapSource>(thumbnail);
                _lruOrder.Enqueue(key);
                EvictIfNeeded();
            }

            return thumbnail;
        }

        /// <summary>
        /// Load a thumbnail asynchronously.
        /// </summary>
        public Task<BitmapSource?> GetThumbnailAsync(string filePath)
        {
            return Task.Run(() => GetThumbnail(filePath));
        }

        /// <summary>
        /// Pin an image in cache so it's never evicted (for favorites, current theme).
        /// </summary>
        public void PinImage(string filePath, BitmapSource image)
        {
            if (_pinnedCache.Count >= MAX_PINNED_CACHE)
            {
                // Evict oldest pinned
                foreach (var key in _pinnedCache.Keys)
                {
                    _pinnedCache.TryRemove(key, out _);
                    break;
                }
            }
            _pinnedCache[filePath.ToLowerInvariant()] = image;
        }

        /// <summary>
        /// Unpin an image from persistent cache.
        /// </summary>
        public void UnpinImage(string filePath)
        {
            _pinnedCache.TryRemove(filePath.ToLowerInvariant(), out _);
        }

        private BitmapSource? LoadThumbnail(string filePath)
        {
            try
            {
                if (!File.Exists(filePath))
                    return null;

                var bitmap = new BitmapImage();
                bitmap.BeginInit();
                bitmap.UriSource = new Uri(filePath, UriKind.Absolute);
                bitmap.DecodePixelWidth = THUMBNAIL_DECODE_WIDTH;
                bitmap.CacheOption = BitmapCacheOption.OnLoad;
                bitmap.CreateOptions = BitmapCreateOptions.IgnoreColorProfile;
                bitmap.EndInit();
                bitmap.Freeze(); // Thread-safe
                return bitmap;
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[ResourceManager] Thumbnail load failed: {filePath} — {ex.Message}");
                return null;
            }
        }

        private void EvictIfNeeded()
        {
            while (_thumbnailCache.Count > MAX_THUMBNAIL_CACHE && _lruOrder.TryDequeue(out var key))
            {
                _thumbnailCache.TryRemove(key, out _);
            }
        }

        #endregion

        #region Video Player Management

        /// <summary>
        /// Register a video player resource for tracking and cleanup.
        /// </summary>
        public void RegisterVideoPlayer(IDisposable player)
        {
            lock (_activeVideoPlayers)
                _activeVideoPlayers.Add(player);
        }

        /// <summary>
        /// Unregister and dispose a video player (call on page leave).
        /// </summary>
        public void ReleaseVideoPlayer(IDisposable player)
        {
            lock (_activeVideoPlayers)
            {
                if (_activeVideoPlayers.Remove(player))
                {
                    try { player.Dispose(); }
                    catch (Exception ex)
                    {
                        Debug.WriteLine($"[ResourceManager] Video dispose error: {ex.Message}");
                    }
                }
            }
        }

        /// <summary>
        /// Dispose all active video players (emergency cleanup).
        /// </summary>
        public void ReleaseAllVideoPlayers()
        {
            lock (_activeVideoPlayers)
            {
                foreach (var player in _activeVideoPlayers)
                {
                    try { player.Dispose(); } catch { }
                }
                _activeVideoPlayers.Clear();
            }
        }

        #endregion

        #region Asset Preloading

        /// <summary>
        /// Preload thumbnails for a batch of file paths in the background.
        /// Useful for preloading adjacent page assets.
        /// </summary>
        public Task PreloadThumbnailsAsync(IEnumerable<string> filePaths, CancellationToken ct = default)
        {
            return Task.Run(() =>
            {
                foreach (var path in filePaths)
                {
                    if (ct.IsCancellationRequested) break;
                    GetThumbnail(path);
                }
            }, ct);
        }

        #endregion

        #region Memory Management

        /// <summary>Get current performance statistics.</summary>
        public PerformanceStats GetStats()
        {
            var process = Process.GetCurrentProcess();
            int videoCount;
            lock (_activeVideoPlayers)
                videoCount = _activeVideoPlayers.Count;

            return new PerformanceStats
            {
                WorkingSetMB = process.WorkingSet64 / (1024 * 1024),
                GcTotalMemoryMB = GC.GetTotalMemory(false) / (1024 * 1024),
                CachedThumbnails = _thumbnailCache.Count,
                CachedImages = _pinnedCache.Count,
                ActiveVideoPlayers = videoCount,
                FrameRate = _currentFps,
                Uptime = Uptime,
            };
        }

        /// <summary>Force a memory cleanup: clear weak refs, run GC.</summary>
        public void ForceCleanup()
        {
            // Clear dead weak references
            var deadKeys = new List<string>();
            foreach (var kvp in _thumbnailCache)
            {
                if (!kvp.Value.TryGetTarget(out _))
                    deadKeys.Add(kvp.Key);
            }
            foreach (var key in deadKeys)
                _thumbnailCache.TryRemove(key, out _);

            // Suggest GC
            GC.Collect(2, GCCollectionMode.Optimized);
            GC.WaitForPendingFinalizers();

            Debug.WriteLine($"[ResourceManager] Cleanup: removed {deadKeys.Count} dead refs, " +
                            $"{_thumbnailCache.Count} cached, {_pinnedCache.Count} pinned");
        }

        private void OnMemoryCheck(object? sender, EventArgs e)
        {
            var process = Process.GetCurrentProcess();
            long memMB = process.WorkingSet64 / (1024 * 1024);

            if (memMB > MEMORY_PRESSURE_THRESHOLD_MB)
            {
                Debug.WriteLine($"[ResourceManager] Memory pressure: {memMB}MB — triggering cleanup");
                ForceCleanup();

                // If still high, release video players
                if (process.WorkingSet64 / (1024 * 1024) > MEMORY_PRESSURE_THRESHOLD_MB)
                {
                    ReleaseAllVideoPlayers();
                    _thumbnailCache.Clear();
                    GC.Collect(2, GCCollectionMode.Aggressive);
                }
            }
        }

        #endregion

        #region Frame Rate Tracking

        private void OnRendering(object? sender, EventArgs e)
        {
            _frameCount++;
            var now = DateTime.UtcNow;
            var elapsed = (now - _lastFpsSample).TotalSeconds;
            if (elapsed >= 1.0)
            {
                _currentFps = _frameCount / elapsed;
                _frameCount = 0;
                _lastFpsSample = now;
            }
        }

        #endregion

        #region Keyboard Accessibility

        /// <summary>
        /// Ensure all interactive controls in the visual tree have proper
        /// keyboard focus and tab navigation. Call on page load.
        /// </summary>
        public static void EnsureKeyboardAccessibility(DependencyObject root)
        {
            if (root == null) return;

            int childCount = VisualTreeHelper.GetChildrenCount(root);
            for (int i = 0; i < childCount; i++)
            {
                var child = VisualTreeHelper.GetChild(root, i);

                if (child is System.Windows.Controls.Button btn)
                {
                    if (!btn.Focusable) btn.Focusable = true;
                    if (btn.IsTabStop == false) btn.IsTabStop = true;
                }
                else if (child is System.Windows.Controls.Primitives.ToggleButton toggle)
                {
                    if (!toggle.Focusable) toggle.Focusable = true;
                }
                else if (child is System.Windows.Controls.TextBox tb)
                {
                    if (!tb.Focusable) tb.Focusable = true;
                }

                EnsureKeyboardAccessibility(child);
            }
        }

        #endregion

        #region Theme Persistence

        private readonly ConcurrentDictionary<string, string> _pageThemes = new();

        /// <summary>Save user's preferred theme for a page.</summary>
        public void SetPageTheme(string pageName, string themePath)
        {
            _pageThemes[pageName] = themePath;
        }

        /// <summary>Get user's preferred theme for a page, or null.</summary>
        public string? GetPageTheme(string pageName)
        {
            return _pageThemes.TryGetValue(pageName, out var path) ? path : null;
        }

        #endregion

        #region IDisposable

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;

            _memoryMonitor.Stop();
            CompositionTarget.Rendering -= OnRendering;
            ReleaseAllVideoPlayers();
            _thumbnailCache.Clear();
            _pinnedCache.Clear();
        }

        #endregion
    }
}
