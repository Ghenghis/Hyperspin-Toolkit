using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Threading;

namespace HyperSpinToolkit.Services
{
    /// <summary>
    /// XInput gamepad button flags matching the native XINPUT_GAMEPAD structure.
    /// </summary>
    [Flags]
    public enum GamepadButton : ushort
    {
        None        = 0x0000,
        DPadUp      = 0x0001,
        DPadDown    = 0x0002,
        DPadLeft    = 0x0004,
        DPadRight   = 0x0008,
        Start       = 0x0010,
        Back        = 0x0020,
        LeftThumb   = 0x0040,
        RightThumb  = 0x0080,
        LeftBumper  = 0x0100,
        RightBumper = 0x0200,
        A           = 0x1000,
        B           = 0x2000,
        X           = 0x4000,
        Y           = 0x8000,
    }

    /// <summary>
    /// Logical arcade actions that gamepad buttons map to.
    /// </summary>
    public enum ArcadeAction
    {
        None,
        NavigateUp,
        NavigateDown,
        NavigateLeft,
        NavigateRight,
        Confirm,          // A
        Cancel,           // B
        AltAction,        // X
        SpecialAction,    // Y
        PreviousPage,     // LB
        NextPage,         // RB
        OpenSettings,     // Start
        ToggleChatOverlay,// Back/Select
        LeftStickUp,
        LeftStickDown,
        LeftStickLeft,
        LeftStickRight,
        RightStickUp,
        RightStickDown,
        RightStickLeft,
        RightStickRight,
        LeftTrigger,
        RightTrigger,
    }

    /// <summary>
    /// Represents a snapshot of a single XInput gamepad state.
    /// </summary>
    public struct GamepadSnapshot
    {
        public GamepadButton Buttons;
        public byte LeftTrigger;
        public byte RightTrigger;
        public short LeftThumbX;
        public short LeftThumbY;
        public short RightThumbX;
        public short RightThumbY;
    }

    /// <summary>
    /// Event args for arcade input actions.
    /// </summary>
    public class ArcadeInputEventArgs : EventArgs
    {
        public ArcadeAction Action { get; }
        public float Magnitude { get; }
        public int PlayerIndex { get; }

        public ArcadeInputEventArgs(ArcadeAction action, float magnitude = 1f, int playerIndex = 0)
        {
            Action = action;
            Magnitude = magnitude;
            PlayerIndex = playerIndex;
        }
    }

    /// <summary>
    /// Singleton XInput gamepad polling service with configurable button mapping,
    /// dead-zone filtering, analog stick processing, and arcade action events.
    /// Uses P/Invoke directly to xinput1_4.dll (zero NuGet dependency).
    /// </summary>
    public sealed class ArcadeInputHandler : IDisposable
    {
        #region Native XInput P/Invoke

        [StructLayout(LayoutKind.Sequential)]
        private struct XINPUT_GAMEPAD
        {
            public ushort wButtons;
            public byte bLeftTrigger;
            public byte bRightTrigger;
            public short sThumbLX;
            public short sThumbLY;
            public short sThumbRX;
            public short sThumbRY;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct XINPUT_STATE
        {
            public uint dwPacketNumber;
            public XINPUT_GAMEPAD Gamepad;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct XINPUT_VIBRATION
        {
            public ushort wLeftMotorSpeed;
            public ushort wRightMotorSpeed;
        }

        [DllImport("xinput1_4.dll", EntryPoint = "XInputGetState")]
        private static extern uint NativeGetState(uint dwUserIndex, ref XINPUT_STATE pState);

        [DllImport("xinput1_4.dll", EntryPoint = "XInputSetState")]
        private static extern uint NativeSetState(uint dwUserIndex, ref XINPUT_VIBRATION pVibration);

        private const uint ERROR_SUCCESS = 0;
        private const uint ERROR_DEVICE_NOT_CONNECTED = 1167;

        #endregion

        #region Singleton

        private static readonly Lazy<ArcadeInputHandler> _instance =
            new(() => new ArcadeInputHandler());

        public static ArcadeInputHandler Instance => _instance.Value;

        #endregion

        #region Fields

        private readonly DispatcherTimer _pollTimer;
        private readonly XINPUT_STATE[] _prevStates = new XINPUT_STATE[4];
        private readonly bool[] _connected = new bool[4];
        private bool _disposed;

        // Dead-zone thresholds
        private const short LEFT_THUMB_DEADZONE  = 7849;
        private const short RIGHT_THUMB_DEADZONE = 8689;
        private const byte  TRIGGER_THRESHOLD    = 30;
        private const short STICK_NAV_THRESHOLD  = 16000;

        // Repeat-rate for held stick/dpad (ms)
        private const int REPEAT_DELAY_MS  = 400;
        private const int REPEAT_RATE_MS   = 120;

        private readonly Dictionary<ArcadeAction, DateTime> _lastRepeat = new();

        // Configurable button mapping
        private Dictionary<GamepadButton, ArcadeAction> _buttonMap;

        #endregion

        #region Events

        /// <summary>Fires when a mapped arcade action is triggered (press or repeat).</summary>
        public event EventHandler<ArcadeInputEventArgs>? ActionTriggered;

        /// <summary>Fires when a gamepad connects or disconnects.</summary>
        public event EventHandler<(int PlayerIndex, bool Connected)>? ConnectionChanged;

        #endregion

        #region Properties

        /// <summary>Poll interval in milliseconds. Default 16ms (~60 Hz).</summary>
        public int PollIntervalMs
        {
            get => (int)_pollTimer.Interval.TotalMilliseconds;
            set => _pollTimer.Interval = TimeSpan.FromMilliseconds(Math.Max(8, value));
        }

        /// <summary>Whether any gamepad is currently connected.</summary>
        public bool AnyConnected => _connected[0] || _connected[1] || _connected[2] || _connected[3];

        /// <summary>Whether polling is active.</summary>
        public bool IsPolling => _pollTimer.IsEnabled;

        #endregion

        #region Constructor

        private ArcadeInputHandler()
        {
            _buttonMap = BuildDefaultMapping();

            _pollTimer = new DispatcherTimer(DispatcherPriority.Input)
            {
                Interval = TimeSpan.FromMilliseconds(16)
            };
            _pollTimer.Tick += OnPollTick;
        }

        #endregion

        #region Public API

        /// <summary>Start polling all 4 player gamepad slots.</summary>
        public void Start()
        {
            if (!_pollTimer.IsEnabled)
                _pollTimer.Start();
        }

        /// <summary>Stop polling.</summary>
        public void Stop()
        {
            _pollTimer.Stop();
        }

        /// <summary>Replace the entire button mapping dictionary.</summary>
        public void SetButtonMapping(Dictionary<GamepadButton, ArcadeAction> mapping)
        {
            _buttonMap = mapping ?? BuildDefaultMapping();
        }

        /// <summary>Remap a single button.</summary>
        public void RemapButton(GamepadButton button, ArcadeAction action)
        {
            _buttonMap[button] = action;
        }

        /// <summary>Get the current button mapping (copy).</summary>
        public Dictionary<GamepadButton, ArcadeAction> GetButtonMapping()
            => new(_buttonMap);

        /// <summary>Vibrate a gamepad. Values 0.0–1.0.</summary>
        public void Vibrate(int playerIndex, float leftMotor, float rightMotor, int durationMs = 200)
        {
            if (playerIndex < 0 || playerIndex > 3) return;
            var vib = new XINPUT_VIBRATION
            {
                wLeftMotorSpeed  = (ushort)(Math.Clamp(leftMotor, 0f, 1f) * 65535),
                wRightMotorSpeed = (ushort)(Math.Clamp(rightMotor, 0f, 1f) * 65535),
            };
            NativeSetState((uint)playerIndex, ref vib);

            // Auto-stop vibration after duration
            if (durationMs > 0)
            {
                var stopTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(durationMs) };
                int idx = playerIndex;
                stopTimer.Tick += (_, _) =>
                {
                    var zero = new XINPUT_VIBRATION();
                    NativeSetState((uint)idx, ref zero);
                    stopTimer.Stop();
                };
                stopTimer.Start();
            }
        }

        /// <summary>Get raw snapshot for a player index.</summary>
        public GamepadSnapshot? GetSnapshot(int playerIndex)
        {
            if (playerIndex < 0 || playerIndex > 3 || !_connected[playerIndex])
                return null;

            var state = new XINPUT_STATE();
            if (NativeGetState((uint)playerIndex, ref state) != ERROR_SUCCESS)
                return null;

            return new GamepadSnapshot
            {
                Buttons     = (GamepadButton)state.Gamepad.wButtons,
                LeftTrigger = state.Gamepad.bLeftTrigger,
                RightTrigger= state.Gamepad.bRightTrigger,
                LeftThumbX  = state.Gamepad.sThumbLX,
                LeftThumbY  = state.Gamepad.sThumbLY,
                RightThumbX = state.Gamepad.sThumbRX,
                RightThumbY = state.Gamepad.sThumbRY,
            };
        }

        /// <summary>Build the default arcade button mapping.</summary>
        public static Dictionary<GamepadButton, ArcadeAction> BuildDefaultMapping()
        {
            return new Dictionary<GamepadButton, ArcadeAction>
            {
                [GamepadButton.DPadUp]      = ArcadeAction.NavigateUp,
                [GamepadButton.DPadDown]    = ArcadeAction.NavigateDown,
                [GamepadButton.DPadLeft]    = ArcadeAction.NavigateLeft,
                [GamepadButton.DPadRight]   = ArcadeAction.NavigateRight,
                [GamepadButton.A]           = ArcadeAction.Confirm,
                [GamepadButton.B]           = ArcadeAction.Cancel,
                [GamepadButton.X]           = ArcadeAction.AltAction,
                [GamepadButton.Y]           = ArcadeAction.SpecialAction,
                [GamepadButton.LeftBumper]  = ArcadeAction.PreviousPage,
                [GamepadButton.RightBumper] = ArcadeAction.NextPage,
                [GamepadButton.Start]       = ArcadeAction.OpenSettings,
                [GamepadButton.Back]        = ArcadeAction.ToggleChatOverlay,
            };
        }

        #endregion

        #region Polling Logic

        private void OnPollTick(object? sender, EventArgs e)
        {
            for (int i = 0; i < 4; i++)
            {
                var state = new XINPUT_STATE();
                uint result = NativeGetState((uint)i, ref state);
                bool wasConnected = _connected[i];
                _connected[i] = result == ERROR_SUCCESS;

                if (wasConnected != _connected[i])
                    ConnectionChanged?.Invoke(this, (i, _connected[i]));

                if (!_connected[i])
                {
                    _prevStates[i] = default;
                    continue;
                }

                // Skip if packet unchanged
                if (state.dwPacketNumber == _prevStates[i].dwPacketNumber)
                    continue;

                ProcessButtons(i, state);
                ProcessAnalogSticks(i, state);
                ProcessTriggers(i, state);

                _prevStates[i] = state;
            }
        }

        private void ProcessButtons(int player, XINPUT_STATE state)
        {
            ushort current = state.Gamepad.wButtons;
            ushort previous = _prevStates[player].Gamepad.wButtons;

            foreach (var kvp in _buttonMap)
            {
                ushort mask = (ushort)kvp.Key;
                bool nowPressed = (current & mask) != 0;
                bool wasPressed = (previous & mask) != 0;

                if (nowPressed && !wasPressed)
                {
                    // Fresh press
                    Fire(kvp.Value, 1f, player);
                    _lastRepeat[kvp.Value] = DateTime.UtcNow.AddMilliseconds(REPEAT_DELAY_MS);
                }
                else if (nowPressed && wasPressed)
                {
                    // Held — check repeat
                    if (_lastRepeat.TryGetValue(kvp.Value, out var nextRepeat) && DateTime.UtcNow >= nextRepeat)
                    {
                        Fire(kvp.Value, 1f, player);
                        _lastRepeat[kvp.Value] = DateTime.UtcNow.AddMilliseconds(REPEAT_RATE_MS);
                    }
                }
                else if (!nowPressed && wasPressed)
                {
                    _lastRepeat.Remove(kvp.Value);
                }
            }
        }

        private void ProcessAnalogSticks(int player, XINPUT_STATE state)
        {
            // Left stick → navigation
            ProcessStick(player,
                state.Gamepad.sThumbLX, state.Gamepad.sThumbLY,
                LEFT_THUMB_DEADZONE,
                ArcadeAction.LeftStickLeft, ArcadeAction.LeftStickRight,
                ArcadeAction.LeftStickDown, ArcadeAction.LeftStickUp);

            // Right stick → camera/zoom
            ProcessStick(player,
                state.Gamepad.sThumbRX, state.Gamepad.sThumbRY,
                RIGHT_THUMB_DEADZONE,
                ArcadeAction.RightStickLeft, ArcadeAction.RightStickRight,
                ArcadeAction.RightStickDown, ArcadeAction.RightStickUp);
        }

        private void ProcessStick(int player, short x, short y, short deadzone,
            ArcadeAction left, ArcadeAction right, ArcadeAction down, ArcadeAction up)
        {
            float normX = ApplyDeadzone(x, deadzone);
            float normY = ApplyDeadzone(y, deadzone);

            if (normX < -0.5f)
                FireWithRepeat(left, Math.Abs(normX), player);
            else if (normX > 0.5f)
                FireWithRepeat(right, normX, player);

            if (normY < -0.5f)
                FireWithRepeat(down, Math.Abs(normY), player);
            else if (normY > 0.5f)
                FireWithRepeat(up, normY, player);
        }

        private void ProcessTriggers(int player, XINPUT_STATE state)
        {
            if (state.Gamepad.bLeftTrigger > TRIGGER_THRESHOLD &&
                _prevStates[player].Gamepad.bLeftTrigger <= TRIGGER_THRESHOLD)
            {
                Fire(ArcadeAction.LeftTrigger, state.Gamepad.bLeftTrigger / 255f, player);
            }
            if (state.Gamepad.bRightTrigger > TRIGGER_THRESHOLD &&
                _prevStates[player].Gamepad.bRightTrigger <= TRIGGER_THRESHOLD)
            {
                Fire(ArcadeAction.RightTrigger, state.Gamepad.bRightTrigger / 255f, player);
            }
        }

        private static float ApplyDeadzone(short value, short deadzone)
        {
            if (Math.Abs(value) < deadzone)
                return 0f;
            float sign = value < 0 ? -1f : 1f;
            return sign * (Math.Abs(value) - deadzone) / (32767f - deadzone);
        }

        private void FireWithRepeat(ArcadeAction action, float magnitude, int player)
        {
            if (!_lastRepeat.TryGetValue(action, out var next) || DateTime.UtcNow >= next)
            {
                Fire(action, magnitude, player);
                _lastRepeat[action] = DateTime.UtcNow.AddMilliseconds(
                    _lastRepeat.ContainsKey(action) ? REPEAT_RATE_MS : REPEAT_DELAY_MS);
            }
        }

        private void Fire(ArcadeAction action, float magnitude, int player)
        {
            ActionTriggered?.Invoke(this, new ArcadeInputEventArgs(action, magnitude, player));

            // Play UI sounds through SoundEffectsEngine
            try
            {
                var sfx = SoundEffectsEngine.Instance;
                switch (action)
                {
                    case ArcadeAction.NavigateUp:
                    case ArcadeAction.NavigateDown:
                    case ArcadeAction.NavigateLeft:
                    case ArcadeAction.NavigateRight:
                    case ArcadeAction.LeftStickUp:
                    case ArcadeAction.LeftStickDown:
                    case ArcadeAction.LeftStickLeft:
                    case ArcadeAction.LeftStickRight:
                        sfx.Play("navigate");
                        break;
                    case ArcadeAction.Confirm:
                        sfx.Play("confirm");
                        break;
                    case ArcadeAction.Cancel:
                        sfx.Play("cancel");
                        break;
                    case ArcadeAction.PreviousPage:
                    case ArcadeAction.NextPage:
                        sfx.Play("page_change");
                        break;
                }
            }
            catch { /* SFX engine not initialized yet */ }
        }

        #endregion

        #region IDisposable

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            _pollTimer.Stop();

            // Zero vibration on all pads
            for (uint i = 0; i < 4; i++)
            {
                var zero = new XINPUT_VIBRATION();
                NativeSetState(i, ref zero);
            }
        }

        #endregion
    }
}
