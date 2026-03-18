using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace HyperSpinToolkit.Services
{
    /// <summary>
    /// Serializable button mapping entry for JSON persistence.
    /// </summary>
    public class ButtonMappingEntry
    {
        [JsonPropertyName("button")]
        public string Button { get; set; } = "";

        [JsonPropertyName("action")]
        public string Action { get; set; } = "";
    }

    /// <summary>
    /// Serializable configuration for gamepad settings including button mappings,
    /// dead-zones, vibration, and transition preferences.
    /// </summary>
    public class GamepadConfig
    {
        [JsonPropertyName("version")]
        public int Version { get; set; } = 1;

        [JsonPropertyName("pollIntervalMs")]
        public int PollIntervalMs { get; set; } = 16;

        [JsonPropertyName("vibrationEnabled")]
        public bool VibrationEnabled { get; set; } = true;

        [JsonPropertyName("vibrationStrength")]
        public float VibrationStrength { get; set; } = 0.5f;

        [JsonPropertyName("transitionStyle")]
        public string TransitionStyle { get; set; } = "PixelDissolve";

        [JsonPropertyName("transitionDurationMs")]
        public int TransitionDurationMs { get; set; } = 400;

        [JsonPropertyName("buttonMappings")]
        public List<ButtonMappingEntry> ButtonMappings { get; set; } = new();
    }

    /// <summary>
    /// Manages loading, saving, and applying gamepad button mapping configuration
    /// from a JSON file in the toolkit config directory.
    /// </summary>
    public static class ButtonMappingConfig
    {
        private static readonly string ConfigDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "HyperSpinToolkit");

        private static readonly string ConfigPath = Path.Combine(ConfigDir, "gamepad_config.json");

        private static readonly JsonSerializerOptions _jsonOptions = new()
        {
            WriteIndented = true,
            PropertyNameCaseInsensitive = true,
        };

        /// <summary>Load config from disk, or return defaults if not found.</summary>
        public static GamepadConfig Load()
        {
            try
            {
                if (File.Exists(ConfigPath))
                {
                    string json = File.ReadAllText(ConfigPath);
                    var config = JsonSerializer.Deserialize<GamepadConfig>(json, _jsonOptions);
                    if (config != null)
                        return config;
                }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[ButtonMappingConfig] Load error: {ex.Message}");
            }

            return CreateDefault();
        }

        /// <summary>Save config to disk.</summary>
        public static void Save(GamepadConfig config)
        {
            try
            {
                Directory.CreateDirectory(ConfigDir);
                string json = JsonSerializer.Serialize(config, _jsonOptions);
                File.WriteAllText(ConfigPath, json);
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[ButtonMappingConfig] Save error: {ex.Message}");
            }
        }

        /// <summary>Apply a saved config to the ArcadeInputHandler and PageTransitionService.</summary>
        public static void Apply(GamepadConfig config)
        {
            // Apply button mappings
            var handler = ArcadeInputHandler.Instance;
            var mapping = new Dictionary<GamepadButton, ArcadeAction>();

            foreach (var entry in config.ButtonMappings)
            {
                if (Enum.TryParse<GamepadButton>(entry.Button, true, out var btn) &&
                    Enum.TryParse<ArcadeAction>(entry.Action, true, out var act))
                {
                    mapping[btn] = act;
                }
            }

            if (mapping.Count > 0)
                handler.SetButtonMapping(mapping);

            handler.PollIntervalMs = config.PollIntervalMs;

            // Apply transition settings
            var transitions = PageTransitionService.Instance;
            if (Enum.TryParse<TransitionStyle>(config.TransitionStyle, true, out var style))
                transitions.DefaultStyle = style;
            transitions.Duration = TimeSpan.FromMilliseconds(config.TransitionDurationMs);
        }

        /// <summary>Create a default config with standard arcade button mappings.</summary>
        public static GamepadConfig CreateDefault()
        {
            var defaultMap = ArcadeInputHandler.BuildDefaultMapping();
            var config = new GamepadConfig();

            foreach (var kvp in defaultMap)
            {
                config.ButtonMappings.Add(new ButtonMappingEntry
                {
                    Button = kvp.Key.ToString(),
                    Action = kvp.Value.ToString(),
                });
            }

            return config;
        }

        /// <summary>Convert current ArcadeInputHandler mapping to a GamepadConfig.</summary>
        public static GamepadConfig CaptureCurrentConfig()
        {
            var handler = ArcadeInputHandler.Instance;
            var transitions = PageTransitionService.Instance;
            var mapping = handler.GetButtonMapping();

            var config = new GamepadConfig
            {
                PollIntervalMs = handler.PollIntervalMs,
                TransitionStyle = transitions.DefaultStyle.ToString(),
                TransitionDurationMs = (int)transitions.Duration.TotalMilliseconds,
            };

            foreach (var kvp in mapping)
            {
                config.ButtonMappings.Add(new ButtonMappingEntry
                {
                    Button = kvp.Key.ToString(),
                    Action = kvp.Value.ToString(),
                });
            }

            return config;
        }

        /// <summary>Reset to defaults and save.</summary>
        public static GamepadConfig ResetToDefaults()
        {
            var config = CreateDefault();
            Save(config);
            Apply(config);
            return config;
        }

        /// <summary>Get the config file path for display in UI.</summary>
        public static string GetConfigPath() => ConfigPath;
    }
}
