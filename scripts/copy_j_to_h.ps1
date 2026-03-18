<#
.SYNOPSIS
    KINHANK Toolkit -- J:\ -> H:\ Game Collection Organizer
.DESCRIPTION
    Copies and organizes all gaming collections from J:\ (20TB backup) to
    H:\ (14TB empty) with a clean, Playnite-ready folder structure.
    Uses robocopy for reliable SATA transfers with resume support.
.NOTES
    - Run sections individually or all at once
    - Safe to re-run: robocopy skips already-copied files
    - Logs saved to H:\_Transfer-Logs\
    - Estimated total: ~1.3TB (H: has 14TB free)
#>

param(
    [ValidateSet("All","PC","Switch","Vita","Retro","Steam","Tools","DryRun")]
    [string]$Section = "All",

    [string]$Source = "J:\",
    [string]$Dest   = "H:\",

    [switch]$WhatIf
)

# -- Config -----------------------------------------------------------------------
$ErrorActionPreference = "Continue"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logDir    = Join-Path $Dest "_Transfer-Logs"
$roboFlags = @("/E", "/Z", "/R:3", "/W:5", "/MT:4", "/NP", "/ETA", "/TEE", "/DCOPY:DAT", "/COPY:DAT")

if ($WhatIf) {
    $roboFlags += "/L"
    Write-Host ">>> DRY RUN MODE -- no files will be copied <<<" -ForegroundColor Yellow
}

# -- Helpers ----------------------------------------------------------------------
function Copy-Collection {
    param(
        [string]$Name,
        [string]$From,
        [string]$To,
        [string]$LogFile
    )
    if (-not (Test-Path $From)) {
        Write-Host "  SKIP: $From (not found)" -ForegroundColor DarkGray
        return
    }
    Write-Host "`n[$Name]" -ForegroundColor Cyan
    Write-Host "  FROM: $From" -ForegroundColor DarkGray
    Write-Host "  TO:   $To" -ForegroundColor DarkGray

    if (-not (Test-Path $logDir)) { New-Item -Path $logDir -ItemType Directory -Force | Out-Null }
    $log = Join-Path $logDir "$LogFile-$timestamp.log"

    $args = @($From, $To) + $roboFlags + @("/LOG+:$log")
    & robocopy @args

    $exitCode = $LASTEXITCODE
    if ($exitCode -le 3) {
        Write-Host "  DONE (robocopy exit: $exitCode)" -ForegroundColor Green
    } elseif ($exitCode -le 7) {
        Write-Host "  DONE with warnings (robocopy exit: $exitCode)" -ForegroundColor Yellow
    } else {
        Write-Host "  ERROR (robocopy exit: $exitCode) -- check $log" -ForegroundColor Red
    }
}

function Copy-SingleFile {
    param(
        [string]$Name,
        [string]$FilePath,
        [string]$DestDir
    )
    if (-not (Test-Path $FilePath)) {
        Write-Host "  SKIP: $FilePath (not found)" -ForegroundColor DarkGray
        return
    }
    if (-not (Test-Path $DestDir)) { New-Item -Path $DestDir -ItemType Directory -Force | Out-Null }
    $destFile = Join-Path $DestDir (Split-Path $FilePath -Leaf)
    if (Test-Path $destFile) {
        Write-Host "  SKIP: $Name (already exists)" -ForegroundColor DarkGray
        return
    }
    Write-Host "  Copying $Name ($([math]::Round((Get-Item $FilePath).Length/1GB,1))GB)..." -ForegroundColor Cyan
    if (-not $WhatIf) {
        Copy-Item $FilePath $DestDir -Force
    }
    Write-Host "  DONE" -ForegroundColor Green
}

# -- Banner -----------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "  KINHANK Toolkit -- Game Collection Transfer (J: -> H:)" -ForegroundColor Magenta
Write-Host "  Section: $Section | Estimated: ~1.3TB -> 14TB drive" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

# =========================================================================
# SECTION: PC Games (~760GB) -- Playnite-ready structure
# =========================================================================
if ($Section -in @("All","PC","DryRun")) {
    Write-Host "=== PC GAMES (~760GB) ===" -ForegroundColor White
    Write-Host "Target: $Dest\PC-Games\" -ForegroundColor DarkGray

    $pcGames = @(
        @{Name="Angry Birds Collection";  Dir="Angry_Birds_collection"},
        @{Name="Cyberpunk 2077";           Dir="Cyberpunk2077"},
        @{Name="ExoCross";                 Dir="ExoCross"},
        @{Name="Expeditions MudRunner";    Dir="Expeditions A MudRunner Game"},
        @{Name="Forza Motorsport";         Dir="Forza Motorsport"},
        @{Name="Ghost of Tsushima DC";     Dir="Ghost of Tsushima DIRECTORS CUT"},
        @{Name="Grand Theft Auto V";       Dir="Grand Theft Auto V"},
        @{Name="GTA San Andreas";          Dir="GTA San Andreas"},
        @{Name="GTA Vice City";            Dir="GTA Vice City"},
        @{Name="Just Cause 4";             Dir="Just Cause 4"},
        @{Name="Microsoft Flight Simulator"; Dir="Microsoft Flight Simulator"},
        @{Name="Red Dead Redemption 2";    Dir="Red Dead Redemption 2"},
        @{Name="Watch Dogs Legion";        Dir="Watch Dogs Legion"},
        @{Name="WRC 8";                    Dir="WRC 8 FIA World Rally Championship"}
    )

    foreach ($game in $pcGames) {
        $src = Join-Path "$Source\Games" $game.Dir
        $dst = Join-Path "$Dest\PC-Games" $game.Name
        Copy-Collection -Name $game.Name -From $src -To $dst -LogFile "PC-$($game.Dir)"
    }

    # Ghost of Tsushima ISO (standalone file in J:\Games root)
    Copy-SingleFile -Name "Ghost of Tsushima ISO" `
        -FilePath "$Source\Games\rune-ghost.of.tsushima.directors.cut.proper.iso" `
        -DestDir "$Dest\PC-Games\Ghost of Tsushima DC"
}

# =========================================================================
# SECTION: Nintendo Switch (~220GB)
# =========================================================================
if ($Section -in @("All","Switch","DryRun")) {
    Write-Host "`n=== NINTENDO SWITCH (~220GB) ===" -ForegroundColor White

    Copy-Collection -Name "Switch SD Backup (256GB)" `
        -From "$Source\Switch_SD_(256GB)" `
        -To "$Dest\Nintendo-Switch\SD-Backup-256GB" `
        -LogFile "Switch-SD"

    Copy-Collection -Name "Switch Games (NSP)" `
        -From "$Source\Switch_Gamez" `
        -To "$Dest\Nintendo-Switch\Games-NSP" `
        -LogFile "Switch-Games"

    Copy-Collection -Name "Switch Cheats" `
        -From "$Source\Switch_Cheat" `
        -To "$Dest\Nintendo-Switch\Cheats" `
        -LogFile "Switch-Cheats"

    Copy-Collection -Name "Switch Saves" `
        -From "$Source\Switch_Saves" `
        -To "$Dest\Nintendo-Switch\Saves" `
        -LogFile "Switch-Saves"

    Copy-Collection -Name "CDNSP-GUI (Switch Tool)" `
        -From "$Source\CDNSP-GUI-Bob-v6.0.2" `
        -To "$Dest\Nintendo-Switch\Tools\CDNSP-GUI-Bob-v6.0.2" `
        -LogFile "Switch-CDNSP"

    Copy-Collection -Name "TegraRcmGUI" `
        -From "$Source\TegraRcmGUI_v2.6_portable" `
        -To "$Dest\Nintendo-Switch\Tools\TegraRcmGUI_v2.6" `
        -LogFile "Switch-Tegra"
}

# =========================================================================
# SECTION: PS Vita (~229GB)
# =========================================================================
if ($Section -in @("All","Vita","DryRun")) {
    Write-Host "`n=== PS VITA (~229GB) ===" -ForegroundColor White

    Copy-Collection -Name "NoPayStation USA Vita" `
        -From "$Source\4TB_Nvme_Backup_Downloads\NoPayStationUSASonyVITA" `
        -To "$Dest\PS-Vita\NoPayStation-USA" `
        -LogFile "Vita-NPS"

    Copy-Collection -Name "PS Vita Retro Ultimate MEGA v3.0" `
        -From "$Source\4TB_Nvme_Backup_Downloads\PS.Vita.Retro.Ultimate.MEGA.Version.3.0-CrazyMac" `
        -To "$Dest\PS-Vita\Retro-Ultimate-MEGA-v3.0" `
        -LogFile "Vita-RetroMega"

    Copy-Collection -Name "PS Vita Retro Themes" `
        -From "$Source\4TB_Nvme_Backup_Downloads\PS.Vita.Retro.Ultimate.THEMES-CrazyMac" `
        -To "$Dest\PS-Vita\Retro-Themes" `
        -LogFile "Vita-Themes"

    Copy-Collection -Name "Vita RetroArch" `
        -From "$Source\4TB_Nvme_Backup_Downloads\retroarch-ps-vita" `
        -To "$Dest\PS-Vita\RetroArch" `
        -LogFile "Vita-RetroArch"

    Copy-Collection -Name "Vita RetroArch Theme" `
        -From "$Source\4TB_Nvme_Backup_Downloads\retroarch_theme_psvita" `
        -To "$Dest\PS-Vita\RetroArch-Theme" `
        -LogFile "Vita-RATheme"

    Copy-Collection -Name "Vita Game Updates" `
        -From "$Source\4TB_Nvme_Backup_Downloads\vita_game_updates" `
        -To "$Dest\PS-Vita\Game-Updates" `
        -LogFile "Vita-Updates"
}

# =========================================================================
# SECTION: Retro Collections (~10GB)
# =========================================================================
if ($Section -in @("All","Retro","DryRun")) {
    Write-Host "`n=== RETRO COLLECTIONS (~10GB) ===" -ForegroundColor White

    Copy-Collection -Name "Nintendo 64 Complete (GoodN64 v3.14)" `
        -From "$Source\4TB_Nvme_Backup_Downloads\Roms.GoodN64.Nintendo.64.V3.14.Complete.GoodMerged.Roms-OneUp" `
        -To "$Dest\Retro\Nintendo-64-GoodN64-v3.14" `
        -LogFile "Retro-N64"

    Copy-Collection -Name "Commodore Amiga ROM Set" `
        -From "$Source\4TB_Nvme_Backup_Downloads\commodore-amiga-rom-set" `
        -To "$Dest\Retro\Commodore-Amiga" `
        -LogFile "Retro-Amiga"

    Copy-Collection -Name "Panasonic 3DO Sampler" `
        -From "$Source\4TB_Nvme_Backup_Downloads\panasonic-3do-the-3do-multi-game-sampler-number-3-europe" `
        -To "$Dest\Retro\Panasonic-3DO" `
        -LogFile "Retro-3DO"

    Copy-Collection -Name "Wii Backups 2022" `
        -From "$Source\4TB_Nvme_Backup_Downloads\Wii_`$27_backups_2022" `
        -To "$Dest\Retro\Nintendo-Wii" `
        -LogFile "Retro-Wii"

    Copy-Collection -Name "EmulationStation Win32" `
        -From "$Source\4TB_Nvme_Backup_Downloads\EmulationStation-Win32" `
        -To "$Dest\Retro\Tools\EmulationStation-Win32" `
        -LogFile "Retro-ES"

    Copy-Collection -Name "RetroArch Frontends & Gaming RetroArch" `
        -From "$Source\4TB_Nvme_Backup_Downloads\retroarch-station_vitamin_dot.tv-with-romset.frontendsanandagaming" `
        -To "$Dest\Retro\RetroArch-Station-ROMSet" `
        -LogFile "Retro-RAStation"

    Copy-Collection -Name "romcenter32" `
        -From "$Source\romcenter32_4.1.1" `
        -To "$Dest\Retro\Tools\romcenter32-4.1.1" `
        -LogFile "Retro-romcenter"
}

# =========================================================================
# SECTION: Steam (~44GB)
# =========================================================================
if ($Section -in @("All","Steam","DryRun")) {
    Write-Host "`n=== STEAM LIBRARY (~44GB) ===" -ForegroundColor White

    Copy-Collection -Name "Steam Library" `
        -From "$Source\SteamLibrary" `
        -To "$Dest\Steam\SteamLibrary" `
        -LogFile "Steam"
}

# =========================================================================
# SECTION: Tools & Utilities
# =========================================================================
if ($Section -in @("All","Tools","DryRun")) {
    Write-Host "`n=== TOOLS & UTILITIES ===" -ForegroundColor White

    Copy-Collection -Name "RetroArch (standalone)" `
        -From "$Source\4TB_Nvme_Backup_Downloads\RetroArch" `
        -To "$Dest\Tools\RetroArch" `
        -LogFile "Tools-RetroArch"

    Copy-Collection -Name "RetroArch 2023-07" `
        -From "$Source\4TB_Nvme_Backup_Downloads\retro-arch_202307" `
        -To "$Dest\Tools\RetroArch-2023-07" `
        -LogFile "Tools-RA2307"

    Copy-Collection -Name "RetroFE 0.10.31" `
        -From "$Source\4TB_Nvme_Backup_Downloads\RetroFE_full_0.10.31(1)" `
        -To "$Dest\Tools\RetroFE-0.10.31" `
        -LogFile "Tools-RetroFE"
}

# -- Summary ----------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Transfer Complete!" -ForegroundColor Green
Write-Host "  Logs: $logDir" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "  H:\ Structure:" -ForegroundColor Green
Write-Host "    PC-Games\        (Playnite-ready, ~760GB)" -ForegroundColor Green
Write-Host "    Nintendo-Switch\ (SD, NSP, Cheats, Saves)" -ForegroundColor Green
Write-Host "    PS-Vita\         (NPS, Retro MEGA, Updates)" -ForegroundColor Green
Write-Host "    Retro\           (N64, Amiga, 3DO, Wii)" -ForegroundColor Green
Write-Host "    Steam\           (SteamLibrary backup)" -ForegroundColor Green
Write-Host "    Tools\           (RetroArch, RetroFE, romcenter)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "To add H:\PC-Games to Playnite:" -ForegroundColor Cyan
Write-Host "  1. Open Playnite -> Library -> Add Games -> Scan Folder"
Write-Host "  2. Point to H:\PC-Games\"
Write-Host "  3. Playnite will auto-detect installed games"
Write-Host ""
