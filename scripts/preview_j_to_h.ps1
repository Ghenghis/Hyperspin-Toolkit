<#
.SYNOPSIS
    Preview what will be copied from J:\ to H:\ -- no files are moved.
.DESCRIPTION
    Scans all gaming collections on J:\ and shows sizes, file counts,
    and the target H:\ structure. Run this BEFORE copy_j_to_h.ps1.
#>

$collections = @(
    @{Category="PC-Games"; Name="Angry Birds Collection"; Source="J:\Games\Angry_Birds_collection"},
    @{Category="PC-Games"; Name="Cyberpunk 2077"; Source="J:\Games\Cyberpunk2077"},
    @{Category="PC-Games"; Name="ExoCross"; Source="J:\Games\ExoCross"},
    @{Category="PC-Games"; Name="Expeditions MudRunner"; Source="J:\Games\Expeditions A MudRunner Game"},
    @{Category="PC-Games"; Name="Forza Motorsport"; Source="J:\Games\Forza Motorsport"},
    @{Category="PC-Games"; Name="Ghost of Tsushima DC"; Source="J:\Games\Ghost of Tsushima DIRECTORS CUT"},
    @{Category="PC-Games"; Name="Grand Theft Auto V"; Source="J:\Games\Grand Theft Auto V"},
    @{Category="PC-Games"; Name="GTA San Andreas"; Source="J:\Games\GTA San Andreas"},
    @{Category="PC-Games"; Name="GTA Vice City"; Source="J:\Games\GTA Vice City"},
    @{Category="PC-Games"; Name="Just Cause 4"; Source="J:\Games\Just Cause 4"},
    @{Category="PC-Games"; Name="Microsoft Flight Simulator"; Source="J:\Games\Microsoft Flight Simulator"},
    @{Category="PC-Games"; Name="Red Dead Redemption 2"; Source="J:\Games\Red Dead Redemption 2"},
    @{Category="PC-Games"; Name="Watch Dogs Legion"; Source="J:\Games\Watch Dogs Legion"},
    @{Category="PC-Games"; Name="WRC 8"; Source="J:\Games\WRC 8 FIA World Rally Championship"},
    @{Category="Nintendo-Switch"; Name="SD Backup 256GB"; Source="J:\Switch_SD_(256GB)"},
    @{Category="Nintendo-Switch"; Name="Switch Games NSP"; Source="J:\Switch_Gamez"},
    @{Category="Nintendo-Switch"; Name="Switch Cheats"; Source="J:\Switch_Cheat"},
    @{Category="Nintendo-Switch"; Name="Switch Saves"; Source="J:\Switch_Saves"},
    @{Category="PS-Vita"; Name="NoPayStation USA"; Source="J:\4TB_Nvme_Backup_Downloads\NoPayStationUSASonyVITA"},
    @{Category="PS-Vita"; Name="Retro Ultimate MEGA v3.0"; Source="J:\4TB_Nvme_Backup_Downloads\PS.Vita.Retro.Ultimate.MEGA.Version.3.0-CrazyMac"},
    @{Category="Retro"; Name="Nintendo 64 GoodN64"; Source="J:\4TB_Nvme_Backup_Downloads\Roms.GoodN64.Nintendo.64.V3.14.Complete.GoodMerged.Roms-OneUp"},
    @{Category="Retro"; Name="Commodore Amiga"; Source="J:\4TB_Nvme_Backup_Downloads\commodore-amiga-rom-set"},
    @{Category="Retro"; Name="Panasonic 3DO"; Source="J:\4TB_Nvme_Backup_Downloads\panasonic-3do-the-3do-multi-game-sampler-number-3-europe"},
    @{Category="Steam"; Name="SteamLibrary"; Source="J:\SteamLibrary"},
    @{Category="Tools"; Name="RetroArch"; Source="J:\4TB_Nvme_Backup_Downloads\RetroArch"},
    @{Category="Tools"; Name="RetroFE 0.10.31"; Source="J:\4TB_Nvme_Backup_Downloads\RetroFE_full_0.10.31(1)"}
)

Write-Host "" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "   J:\ -> H:\ Gaming Collection Preview" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

$grandTotal = 0
$currentCat = ""

foreach ($c in $collections) {
    if ($c.Category -ne $currentCat) {
        $currentCat = $c.Category
        Write-Host "`n  -- H:\$currentCat\ --" -ForegroundColor Cyan
    }
    if (Test-Path $c.Source) {
        $files = Get-ChildItem $c.Source -Recurse -File -ErrorAction SilentlyContinue
        $sizeGB = [math]::Round(($files | Measure-Object Length -Sum).Sum / 1GB, 1)
        $grandTotal += $sizeGB
        Write-Host ("    {0,8}GB | {1,6} files | {2}" -f $sizeGB, $files.Count, $c.Name) -ForegroundColor White
    } else {
        Write-Host ("    {0,8}   | {1,6}       | {2} (NOT FOUND)" -f "--", "--", $c.Name) -ForegroundColor DarkGray
    }
}

Write-Host "`n  =========================================" -ForegroundColor Yellow
Write-Host ("  TOTAL: {0}GB (~{1}TB)" -f [math]::Round($grandTotal,1), [math]::Round($grandTotal/1024,2)) -ForegroundColor Yellow

$hDrive = Get-PSDrive H -ErrorAction SilentlyContinue
if ($hDrive) {
    $freeGB = [math]::Round($hDrive.Free / 1GB, 0)
    if ($grandTotal -lt $freeGB) {
        $spaceMsg = "PLENTY OF ROOM"; $spaceColor = "Green"
    } else {
        $spaceMsg = "NOT ENOUGH SPACE!"; $spaceColor = "Red"
    }
    Write-Host "  H:\ free: ${freeGB}GB - $spaceMsg" -ForegroundColor $spaceColor
}

Write-Host "`n  To start the transfer:" -ForegroundColor DarkGray
Write-Host "    .\copy_j_to_h.ps1 -Section All       # Copy everything" -ForegroundColor DarkGray
Write-Host "    .\copy_j_to_h.ps1 -Section PC         # PC games only" -ForegroundColor DarkGray
Write-Host "    .\copy_j_to_h.ps1 -Section Switch      # Switch only" -ForegroundColor DarkGray
Write-Host "    .\copy_j_to_h.ps1 -Section Vita        # PS Vita only" -ForegroundColor DarkGray
Write-Host "    .\copy_j_to_h.ps1 -Section All -WhatIf # Dry run" -ForegroundColor DarkGray
Write-Host ""
