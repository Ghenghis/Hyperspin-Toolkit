using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Windows.Media;

namespace HyperSpinToolkit.Services
{
    /// <summary>
    /// M47 — Sound Effects Engine: Load arcade sounds from Media/{System}/Sound/ (20K files).
    /// UI sound map: click, hover, navigate, transition, success, error, ambient.
    /// Sound presets per page theme. Volume control + mute toggle.
    /// </summary>
    public sealed class SoundEffectsEngine
    {
        private static readonly Lazy<SoundEffectsEngine> _instance = new(() => new SoundEffectsEngine());
        public static SoundEffectsEngine Instance => _instance.Value;

        private readonly ConcurrentDictionary<string, MediaPlayer> _pool = new();
        private readonly ConcurrentDictionary<string, string> _soundMap = new();
        private readonly List<string> _searchPaths = new();
        private double _volume = 0.5;
        private bool _isMuted;

        // ── UI Sound Event Keys ──
        public const string SfxClick = "ui.click";
        public const string SfxHover = "ui.hover";
        public const string SfxNavigate = "ui.navigate";
        public const string SfxTransition = "ui.transition";
        public const string SfxSuccess = "ui.success";
        public const string SfxError = "ui.error";
        public const string SfxAmbient = "ui.ambient";
        public const string SfxStartup = "ui.startup";
        public const string SfxShutdown = "ui.shutdown";

        private SoundEffectsEngine()
        {
            // Default search paths for arcade sounds
            _searchPaths.AddRange(new[]
            {
                @"D:\Arcade\HyperSpin\Media",
                @"D:\Arcade\RocketLauncher\Media",
            });
        }

        // ── Configuration ──

        public double Volume
        {
            get => _volume;
            set => _volume = Math.Clamp(value, 0.0, 1.0);
        }

        public bool IsMuted
        {
            get => _isMuted;
            set => _isMuted = value;
        }

        public void ToggleMute() => _isMuted = !_isMuted;

        public void AddSearchPath(string path)
        {
            if (!_searchPaths.Contains(path))
                _searchPaths.Add(path);
        }

        // ── Sound Map ──

        /// <summary>
        /// Map a UI event key to a sound file path.
        /// </summary>
        public void MapSound(string eventKey, string filePath)
        {
            if (File.Exists(filePath))
                _soundMap[eventKey] = filePath;
        }

        /// <summary>
        /// Auto-discover and map sounds from a system's Sound directory.
        /// </summary>
        public int LoadSystemSounds(string system)
        {
            int loaded = 0;
            foreach (var basePath in _searchPaths)
            {
                var soundDir = Path.Combine(basePath, system, "Sound");
                if (!Directory.Exists(soundDir))
                    continue;

                foreach (var file in Directory.EnumerateFiles(soundDir, "*.*", SearchOption.AllDirectories))
                {
                    string ext = Path.GetExtension(file).ToLowerInvariant();
                    if (ext is ".mp3" or ".wav" or ".ogg" or ".wma")
                    {
                        string key = $"{system}.{Path.GetFileNameWithoutExtension(file).ToLowerInvariant()}";
                        _soundMap.TryAdd(key, file);
                        loaded++;
                    }
                }
            }
            return loaded;
        }

        /// <summary>
        /// Load a preset theme mapping for UI sounds.
        /// </summary>
        public void LoadPreset(SoundPreset preset)
        {
            // Map generic UI sounds based on preset
            string system = preset switch
            {
                SoundPreset.MAME => "MAME",
                SoundPreset.Nintendo => "Nintendo Entertainment System",
                SoundPreset.Sega => "Sega Genesis",
                SoundPreset.Atari => "Atari 2600",
                SoundPreset.Neo_Geo => "SNK Neo Geo",
                _ => "MAME",
            };

            // Try to find suitable files
            foreach (var basePath in _searchPaths)
            {
                var soundDir = Path.Combine(basePath, system, "Sound");
                if (!Directory.Exists(soundDir)) continue;

                MapFirstFound(SfxClick, soundDir, new[] { "click", "coin", "select" });
                MapFirstFound(SfxHover, soundDir, new[] { "hover", "move", "cursor" });
                MapFirstFound(SfxNavigate, soundDir, new[] { "navigate", "scroll", "menu" });
                MapFirstFound(SfxTransition, soundDir, new[] { "transition", "whoosh", "swipe" });
                MapFirstFound(SfxSuccess, soundDir, new[] { "success", "win", "complete", "1up" });
                MapFirstFound(SfxError, soundDir, new[] { "error", "fail", "wrong", "die" });
                MapFirstFound(SfxStartup, soundDir, new[] { "startup", "intro", "start" });
                break;
            }
        }

        private void MapFirstFound(string eventKey, string dir, string[] searchTerms)
        {
            foreach (var term in searchTerms)
            {
                foreach (var file in Directory.EnumerateFiles(dir, $"*{term}*.*"))
                {
                    string ext = Path.GetExtension(file).ToLowerInvariant();
                    if (ext is ".mp3" or ".wav" or ".ogg" or ".wma")
                    {
                        _soundMap[eventKey] = file;
                        return;
                    }
                }
            }
        }

        // ── Playback ──

        /// <summary>
        /// Play a sound by event key. Non-blocking.
        /// </summary>
        public void Play(string eventKey)
        {
            if (_isMuted || _volume <= 0) return;
            if (!_soundMap.TryGetValue(eventKey, out var path)) return;
            if (!File.Exists(path)) return;

            try
            {
                // Use a fresh MediaPlayer for overlapping sounds
                var player = new MediaPlayer();
                player.Volume = _volume;
                player.Open(new Uri(path, UriKind.Absolute));
                player.Play();

                // Clean up when done
                player.MediaEnded += (_, _) => { player.Close(); };
                player.MediaFailed += (_, _) => { player.Close(); };
            }
            catch
            {
                // Silently fail — sound is non-critical
            }
        }

        /// <summary>
        /// Play a sound file directly by path.
        /// </summary>
        public void PlayFile(string filePath)
        {
            if (_isMuted || _volume <= 0 || !File.Exists(filePath)) return;
            try
            {
                var player = new MediaPlayer();
                player.Volume = _volume;
                player.Open(new Uri(filePath, UriKind.Absolute));
                player.Play();
                player.MediaEnded += (_, _) => { player.Close(); };
            }
            catch { }
        }

        // ── Status ──

        public Dictionary<string, string> GetSoundMap() => new(_soundMap);

        public int MappedSoundCount => _soundMap.Count;

        public SoundEngineStatus GetStatus() => new()
        {
            Volume = _volume,
            IsMuted = _isMuted,
            MappedSounds = _soundMap.Count,
            SearchPaths = new List<string>(_searchPaths),
        };
    }

    public class SoundEngineStatus
    {
        public double Volume { get; init; }
        public bool IsMuted { get; init; }
        public int MappedSounds { get; init; }
        public List<string> SearchPaths { get; init; } = new();
    }

    public enum SoundPreset
    {
        MAME,
        Nintendo,
        Sega,
        Atari,
        Neo_Geo,
        Silent,
    }
}
