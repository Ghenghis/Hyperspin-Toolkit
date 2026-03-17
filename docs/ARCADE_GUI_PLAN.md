# Arcade GUI Plan — SOTA C#/WPF Interface

> **Last Updated:** 2026-03-17  
> **Status:** Design Phase  
> **Stack:** C# / WPF / .NET 8+ / SharpDX or HelixToolkit (3D) / LibVLCSharp (video)

---

## Vision

Transform the HyperSpin Toolkit from a CLI/dashboard tool into a **state-of-the-art arcade cabinet interface** that uses actual game assets from the ROM collection HDDs (301K PNGs, 47K videos, 20K audio, 8K SWF themes) for every visual element. The GUI should feel like sitting at a premium arcade cabinet — animated backgrounds, spinning wheel art, video previews, neon effects, particle systems, and smooth transitions on every page.

---

## Asset Inventory (Available Across HDDs)

### D:\Arcade\Media (HyperSpin Collection)
| Asset Type                | Count | Format         | Location                              |
| ------------------------- | ----- | -------------- | ------------------------------------- |
| **Wheel Art**             | ~45K+ | PNG            | `Media\{System}\Images\Wheel\`        |
| **Backgrounds**           | ~15K+ | PNG            | `Media\{System}\Images\Backgrounds\`  |
| **Box Art (Artwork 1-4)** | ~80K+ | PNG (4 layers) | `Media\{System}\Images\Artwork{1-4}\` |
| **Genre Icons**           | ~2K+  | PNG            | `Media\{System}\Images\Genre\`        |
| **Letter Art**            | ~500+ | PNG            | `Media\{System}\Images\Letters\`      |
| **Special Art**           | ~5K+  | PNG            | `Media\{System}\Images\Special\`      |
| **Animated Themes**       | ~8K   | SWF/ZIP        | `Media\{System}\Themes\`              |
| **Preview Videos**        | ~47K  | MP4/FLV        | `Media\{System}\Video\`               |
| **Sound Effects**         | ~20K  | MP3/WAV        | `Media\{System}\Sound\`               |

### K:\Arcade\menu-art (Attract Mode Collection)
| Asset Type           | Format  | Location                            |
| -------------------- | ------- | ----------------------------------- |
| Fanart               | PNG/JPG | `menu-art\fanart\`                  |
| Flyers               | PNG/JPG | `menu-art\flyer\`                   |
| Marquees             | PNG/JPG | `menu-art\marquee\`                 |
| Snaps (screenshots)  | PNG     | `menu-art\snap\`                    |
| Themes               | Various | `menu-art\themes\`                  |
| Override Transitions | Various | `menu-art\override transitions\`    |
| Music                | MP3     | `menu-art\music\`                   |
| Collection Art       | PNG     | `menu-art\{Collection} Collection\` |

### L:\CORE - TYPE R (LaunchBox Collection)
| Asset Type     | Location                           |
| -------------- | ---------------------------------- |
| System Artwork | `collections\Main\system_artwork\` |
| Menu Assets    | `collections\Main\menu\`           |
| Playlists      | `collections\Main\playlists\`      |

### N:\roms (Batocera Collection)
| Asset Type         | Location       |
| ------------------ | -------------- |
| Themes             | `themes\`      |
| Decorations/Bezels | `decorations\` |
| Splash Screens     | `splash\`      |

---

## GUI Architecture

### Page Structure

```
┌─────────────────────────────────────────────────────────┐
│                    ARCADE SHELL                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  ANIMATED BACKGROUND LAYER                          │ │
│  │  (Video loop or particle system from game themes)   │ │
│  │  ┌───────────────────────────────────────────────┐  │ │
│  │  │  CONTENT LAYER                                │  │ │
│  │  │                                               │  │ │
│  │  │   Page-specific content with arcade styling   │  │ │
│  │  │                                               │  │ │
│  │  └───────────────────────────────────────────────┘  │ │
│  │  ┌───────────────────────────────────────────────┐  │ │
│  │  │  HUD OVERLAY                                  │  │ │
│  │  │  Agent status │ Drive health │ System clock   │  │ │
│  │  └───────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  NAV BAR (Arcade button strip with glow effects)    │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Pages (All Arcade-Themed)

| Page                   | Purpose                              | Key Visuals                                                        |
| ---------------------- | ------------------------------------ | ------------------------------------------------------------------ |
| **Dashboard**          | System overview + agent status       | Animated system wheel, drive health gauges, neon score-style stats |
| **Collection Browser** | Browse all systems/games             | HyperSpin-style spinning wheel with video previews                 |
| **Drive Manager**      | HDD inventory + health               | Arcade-style meter gauges, LED indicators per drive                |
| **Agent Console**      | Goose/NemoClaw/OpenHands status      | Terminal-style with CRT scan-line effect                           |
| **Asset Gallery**      | Browse/search all game assets        | Grid view with lightbox, filtering by type/system                  |
| **Update Center**      | Emulator updates + rollback          | Progress bars styled as arcade loading screens                     |
| **ROM Audit**          | ROM completeness + duplicates        | Pac-Man-style completion meter per system                          |
| **Backup Control**     | Clone/sync operations                | Transfer progress with animated pixel art                          |
| **Settings**           | LLM config, drive registry, policies | Retro options menu with joystick-style navigation                  |
| **AI Chat**            | Natural language interface           | Arcade-style chat bubble with scanline text                        |

---

## Visual Design System

### Theme Engine

The GUI dynamically loads themes from the game asset libraries:

```csharp
public class ArcadeThemeEngine
{
    // Scans all registered drives for available themes
    private readonly DriveRegistry _registry;
    private readonly AssetIndex _assetIndex;
    
    // Theme sources in priority order
    public List<ThemeSource> Sources => new()
    {
        new("D:\\Arcade\\Media", ThemeType.HyperSpin),
        new("K:\\Arcade\\menu-art", ThemeType.AttractMode),
        new("L:\\CORE - TYPE R\\collections\\Main", ThemeType.LaunchBox),
        new("N:\\themes", ThemeType.Batocera),
    };
    
    // Get random background for a page
    public async Task<BitmapSource> GetBackground(string page)
    {
        var candidates = _assetIndex.Query(
            assetType: AssetType.Background,
            minResolution: new Size(1920, 1080),
            preferSystems: GetPageRelevantSystems(page)
        );
        return await LoadAndCache(candidates.Random());
    }
    
    // Get animated theme for a system
    public async Task<ThemeAnimation> GetSystemTheme(string system)
    {
        // Check SWF themes first (convert to Lottie/XAML animation)
        // Fall back to video loop
        // Fall back to static background + particle effects
    }
    
    // Get wheel art for navigation
    public async Task<BitmapSource> GetWheelArt(string system)
    {
        return await LoadFromPath(
            $"D:\\Arcade\\Media\\{system}\\Images\\Wheel"
        );
    }
}
```

### Visual Effects Library

| Effect                    | Implementation                    | Usage                             |
| ------------------------- | --------------------------------- | --------------------------------- |
| **CRT Scanlines**         | HLSL pixel shader                 | Agent console, retro pages        |
| **Neon Glow**             | WPF DropShadowEffect + BlurEffect | Buttons, headers, active elements |
| **Particle System**       | Custom WPF particle engine        | Backgrounds, transitions          |
| **Spinning Wheel**        | 3D transform + carousel control   | Collection browser navigation     |
| **Video Background**      | LibVLCSharp MediaElement          | Dashboard, system pages           |
| **Pixel Dissolve**        | Custom transition shader          | Page transitions                  |
| **Arcade Marquee Scroll** | TextBlock animation               | Status bar, notifications         |
| **LED Indicators**        | Custom control with glow states   | Drive health, agent status        |
| **Score Counter**         | Animated number roller            | Statistics, counters              |
| **Joystick Nav**          | Gamepad input handler             | Full gamepad/joystick support     |

### Color Palette (Arcade Neon)

```csharp
public static class ArcadeColors
{
    // Primary neon palette
    public static Color NeonBlue    = Color.FromRgb(0x00, 0xD4, 0xFF);
    public static Color NeonPink    = Color.FromRgb(0xFF, 0x00, 0x88);
    public static Color NeonGreen   = Color.FromRgb(0x39, 0xFF, 0x14);
    public static Color NeonYellow  = Color.FromRgb(0xFF, 0xF0, 0x00);
    public static Color NeonOrange  = Color.FromRgb(0xFF, 0x6E, 0x00);
    public static Color NeonPurple  = Color.FromRgb(0xBF, 0x00, 0xFF);
    
    // Background
    public static Color DarkCabinet = Color.FromRgb(0x0A, 0x0A, 0x14);
    public static Color DarkPanel   = Color.FromRgb(0x12, 0x12, 0x1E);
    
    // Health status
    public static Color HealthGood    = NeonGreen;
    public static Color HealthWarning = NeonYellow;
    public static Color HealthBad     = NeonPink;
    
    // Accent gradients
    public static LinearGradientBrush ArcadeGradient => 
        new(NeonBlue, NeonPurple, 45);
}
```

### Typography

```csharp
// Primary: "Press Start 2P" (pixel/arcade font)
// Secondary: "Orbitron" (futuristic, clean)
// Monospace: "JetBrains Mono" (agent console, code)
// Fallback: "Segoe UI" (Windows default)
```

---

## Asset Audit Engine

### Purpose
Scan all gaming HDDs to build a searchable index of every visual, audio, and animation asset. The index powers the Arcade GUI theme engine and allows agents to recommend the best assets for each page.

### Engine: `engines/asset_auditor.py`

```python
# Asset types to index
ASSET_TYPES = {
    "wheel_art":    ("Images/Wheel", [".png"]),
    "background":   ("Images/Backgrounds", [".png", ".jpg"]),
    "box_art":      ("Images/Artwork*", [".png", ".jpg"]),
    "genre_icon":   ("Images/Genre", [".png"]),
    "special_art":  ("Images/Special", [".png"]),
    "theme_anim":   ("Themes", [".swf", ".zip"]),
    "video":        ("Video", [".mp4", ".flv", ".avi"]),
    "audio":        ("Sound", [".mp3", ".wav", ".ogg"]),
    "fanart":       ("fanart", [".png", ".jpg"]),
    "marquee":      ("marquee", [".png", ".jpg"]),
    "flyer":        ("flyer", [".png", ".jpg"]),
    "snap":         ("snap", [".png"]),
    "bezel":        ("decorations", [".png", ".cfg"]),
}

# Quality scoring criteria
QUALITY_METRICS = {
    "resolution": "Higher resolution = higher score",
    "aspect_ratio": "16:9 or 4:3 preferred for backgrounds",
    "file_size": "Larger = likely higher quality",
    "animation": "Animated themes score highest",
    "video_duration": "5-30 second previews score highest",
}
```

### Asset Index Schema

```json
{
    "asset_id": "sha256_first8",
    "path": "D:\\Arcade\\Media\\MAME\\Images\\Wheel\\pacman.png",
    "drive_tag": "TEST_HYPERSPIN",
    "system": "MAME",
    "game": "pacman",
    "type": "wheel_art",
    "format": "png",
    "width": 400,
    "height": 300,
    "file_size_kb": 85,
    "quality_score": 8.5,
    "gui_usable": true,
    "recommended_for": ["collection_browser", "dashboard"]
}
```

### Audit Workflow

1. **Scan** — Walk all `Media/`, `menu-art/`, `system_artwork/`, `themes/` directories
2. **Index** — Record path, type, format, dimensions, file size
3. **Score** — Calculate quality score per asset
4. **Classify** — Tag assets by GUI page relevance
5. **Report** — Generate asset inventory report with recommendations
6. **Cache** — Create optimized thumbnails for GUI (resized, pre-loaded)

---

## SWF Theme Conversion Strategy

HyperSpin's 8K+ SWF animated themes are a massive visual asset but need conversion for WPF:

| Approach                         | Pros                                 | Cons                                 |
| -------------------------------- | ------------------------------------ | ------------------------------------ |
| **JPEXS → Lottie JSON**          | Native WPF rendering via LottieSharp | Complex SWFs may not convert cleanly |
| **SWF → MP4 video**              | Simple playback via LibVLCSharp      | Loses interactivity, larger files    |
| **SWF → XAML Storyboard**        | Native WPF animations                | Manual/complex conversion            |
| **SWF → Sprite sheets**          | Lightweight, fast rendering          | Loses vector quality                 |
| **Embedded Chromium (CefSharp)** | Perfect SWF rendering                | Heavy resource usage                 |

**Recommended Approach:** Hybrid
1. Convert top 100 most-used themes to Lottie JSON (automated via JPEXS CLI)
2. Convert remaining to MP4 video loops (batch via FFmpeg)
3. Use CefSharp fallback for complex interactive themes
4. Generate static PNG snapshots for thumbnails/previews

---

## Gamepad/Joystick Support

The Arcade GUI should support full gamepad/joystick navigation:

```csharp
public class ArcadeInputHandler
{
    // Map gamepad buttons to GUI actions
    public Dictionary<GamepadButton, Action> ButtonMap => new()
    {
        [GamepadButton.DPadUp]    = () => NavigateUp(),
        [GamepadButton.DPadDown]  = () => NavigateDown(),
        [GamepadButton.DPadLeft]  = () => NavigateLeft(),
        [GamepadButton.DPadRight] = () => NavigateRight(),
        [GamepadButton.A]         = () => Select(),        // Green button
        [GamepadButton.B]         = () => Back(),          // Red button
        [GamepadButton.X]         = () => QuickAction(),   // Blue button
        [GamepadButton.Y]         = () => ContextMenu(),   // Yellow button
        [GamepadButton.Start]     = () => OpenSettings(),
        [GamepadButton.Select]    = () => ToggleAgentChat(),
        [GamepadButton.LB]        = () => PreviousPage(),
        [GamepadButton.RB]        = () => NextPage(),
    };
    
    // Joystick analog for smooth scrolling
    // Left stick = wheel/list navigation
    // Right stick = camera/zoom in 3D views
}
```

---

## Project Structure (C#/WPF)

```
D:\hyperspin_toolkit\gui\
├── HyperSpinToolkit.sln
├── HyperSpinToolkit.App\
│   ├── App.xaml
│   ├── MainWindow.xaml              (Arcade shell with layers)
│   ├── Views\
│   │   ├── DashboardView.xaml       (Main dashboard)
│   │   ├── CollectionBrowserView.xaml (Spinning wheel browser)
│   │   ├── DriveManagerView.xaml    (HDD inventory with gauges)
│   │   ├── AgentConsoleView.xaml    (CRT-style agent terminal)
│   │   ├── AssetGalleryView.xaml    (Media browser)
│   │   ├── UpdateCenterView.xaml    (Emulator updates)
│   │   ├── RomAuditView.xaml        (Completeness tracking)
│   │   ├── BackupControlView.xaml   (Clone/sync progress)
│   │   ├── SettingsView.xaml        (Retro options menu)
│   │   └── AiChatView.xaml          (NL chat interface)
│   ├── Controls\
│   │   ├── ArcadeButton.xaml        (Neon glow button)
│   │   ├── WheelCarousel.xaml       (3D spinning wheel)
│   │   ├── NeonGauge.xaml           (Arcade-style gauge)
│   │   ├── LedIndicator.xaml        (Multi-color LED)
│   │   ├── ScoreCounter.xaml        (Animated number roller)
│   │   ├── CrtTerminal.xaml         (Scanline terminal)
│   │   ├── VideoBackground.xaml     (LibVLC video loop)
│   │   └── ParticleCanvas.xaml      (Particle effects)
│   ├── Themes\
│   │   ├── ArcadeTheme.xaml         (Global arcade styles)
│   │   ├── NeonColors.xaml          (Color palette)
│   │   └── ArcadeFonts.xaml         (Font definitions)
│   ├── Effects\
│   │   ├── CrtScanlineEffect.cs     (HLSL shader)
│   │   ├── NeonGlowEffect.cs        (Glow shader)
│   │   └── PixelDissolveEffect.cs   (Transition shader)
│   ├── Services\
│   │   ├── ThemeEngine.cs            (Dynamic theme loading)
│   │   ├── AssetIndexService.cs      (Asset database queries)
│   │   ├── AgentBridgeService.cs     (Goose/NemoClaw WebSocket)
│   │   ├── DriveRegistryService.cs   (drive_registry.json reader)
│   │   └── GamepadService.cs         (Input handling)
│   └── ViewModels\
│       ├── DashboardViewModel.cs
│       ├── CollectionViewModel.cs
│       ├── DriveManagerViewModel.cs
│       └── ... (MVVM pattern)
├── HyperSpinToolkit.Core\            (Shared library)
│   ├── Models\
│   ├── Interfaces\
│   └── Helpers\
└── HyperSpinToolkit.Tests\           (Unit tests)
```

---

## Implementation Phases

### Phase G1: Foundation (Weeks 1-2)
- [ ] Create .NET 8 WPF solution structure
- [ ] Implement ArcadeTheme.xaml with neon color palette
- [ ] Build ArcadeButton, NeonGauge, LedIndicator controls
- [ ] Create MainWindow shell with layered architecture
- [ ] Implement VideoBackground control with LibVLCSharp
- [ ] Add Press Start 2P and Orbitron fonts

### Phase G2: Dashboard (Weeks 2-3)
- [ ] Build DashboardView with drive health gauges
- [ ] Implement ScoreCounter for collection statistics
- [ ] Add agent status indicators (LED controls)
- [ ] Connect to drive_registry.json via DriveRegistryService
- [ ] Add animated background from random game theme

### Phase G3: Collection Browser (Weeks 3-5)
- [ ] Build WheelCarousel 3D control (spinning wheel art)
- [ ] Implement system navigation with wheel art from Media/
- [ ] Add video preview panel (MP4 from Media/{System}/Video/)
- [ ] Implement sound effects on navigation (Media/{System}/Sound/)
- [ ] Add box art display panels (Artwork1-4)
- [ ] Connect to ROM audit data for game counts

### Phase G4: Asset Integration (Weeks 5-7)
- [ ] Build AssetIndexService connected to asset_auditor.py output
- [ ] Implement dynamic theme loading from all HDDs
- [ ] Build AssetGalleryView with filtering/search
- [ ] Create thumbnail cache for fast browsing
- [ ] SWF → Lottie conversion pipeline for top themes
- [ ] SWF → MP4 batch conversion for remaining themes

### Phase G5: Agent Integration (Weeks 7-9)
- [ ] Build AgentBridgeService (WebSocket to Goose/MCP Bridge)
- [ ] Implement AgentConsoleView with CRT scanline effect
- [ ] Add real-time agent status in HUD overlay
- [ ] Build AiChatView for natural language commands
- [ ] Connect agent results to GUI (audit reports, recommendations)

### Phase G6: Full Arcade Experience (Weeks 9-12)
- [ ] Implement all remaining pages (Update Center, Backup Control, etc.)
- [ ] Add CRT scanline HLSL shader
- [ ] Add neon glow HLSL shader
- [ ] Add pixel dissolve page transitions
- [ ] Add particle system for backgrounds
- [ ] Implement full gamepad/joystick support
- [ ] Polish all animations and transitions
- [ ] Performance optimization (asset preloading, caching)
- [ ] End-to-end testing with all agents active
