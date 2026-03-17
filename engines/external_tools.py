"""External Tools Wrapper — integrates CLI-based ROM/media management tools.

Provides Python wrappers for:
  - Igir (ROM collection manager)
  - ClrMamePro / RomVault (ROM verification)
  - Flips (IPS/BPS ROM patching)
  - Skyscraper (media scraper)
  - MAME CLI (listxml, verifyroms)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from core.logger import get_logger, audit
from core.config import get

log = get_logger("external_tools")


def _which(name: str) -> Optional[str]:
    """Find executable on PATH or known locations."""
    found = shutil.which(name)
    if found:
        return found

    # Check common install locations
    known = {
        "igir": [r"C:\Users\Admin\AppData\Roaming\npm\igir.cmd"],
        "mame64": [
            str(Path(get("paths.emulators_root", r"D:\Arcade\emulators")) / "MAME" / "mame64.exe"),
        ],
        "flips": [r"D:\hyperspin_toolkit\tools\flips.exe"],
    }
    for loc in known.get(name, []):
        if Path(loc).exists():
            return loc
    return None


def _run(cmd: list[str], cwd: Optional[str] = None, timeout: int = 600) -> dict:
    """Run a subprocess and capture output."""
    log.info("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        log.error("Command timed out after %ds: %s", timeout, cmd[0])
        return {"returncode": -1, "stdout": "", "stderr": "timeout", "success": False}
    except FileNotFoundError:
        log.error("Command not found: %s", cmd[0])
        return {"returncode": -1, "stdout": "", "stderr": "not found", "success": False}
    except Exception as exc:
        log.error("Command failed: %s", exc)
        return {"returncode": -1, "stdout": "", "stderr": str(exc), "success": False}


# ── MAME CLI Integration ────────────────────────────────────────────

class MAMETool:
    """Wrapper for MAME command-line operations."""

    def __init__(self, mame_exe: Optional[str] = None):
        self.exe = mame_exe or _which("mame64")
        if not self.exe or not Path(self.exe).exists():
            log.warning("MAME executable not found")

    @property
    def available(self) -> bool:
        return self.exe is not None and Path(self.exe).exists()

    def get_version(self) -> Optional[str]:
        """Get MAME version string."""
        if not self.available:
            return None
        result = _run([self.exe, "-help"], timeout=10)
        if result["success"] and result["stdout"]:
            import re
            m = re.search(r"MAME v?([\d.]+)", result["stdout"])
            return m.group(1) if m else result["stdout"].split("\n")[0]
        return None

    def list_xml(self, output_file: str) -> dict:
        """Generate MAME listxml DAT file for ROM auditing."""
        if not self.available:
            return {"success": False, "stderr": "MAME not found"}
        log.info("Generating MAME listxml (this may take a while)...")
        result = _run([self.exe, "-listxml"], timeout=300)
        if result["success"]:
            Path(output_file).write_text(result["stdout"], encoding="utf-8")
            size_mb = Path(output_file).stat().st_size / 1048576
            log.info("listxml written: %s (%.1f MB)", output_file, size_mb)
            audit("mame_listxml", output_file)
        return result

    def verify_roms(self, rompath: Optional[str] = None) -> dict:
        """Run MAME ROM verification."""
        if not self.available:
            return {"success": False, "stderr": "MAME not found"}
        cmd = [self.exe, "-verifyroms"]
        if rompath:
            cmd.extend(["-rompath", rompath])
        log.info("Verifying MAME ROMs (this may take a while)...")
        result = _run(cmd, timeout=600)
        if result["stdout"]:
            lines = result["stdout"].strip().split("\n")
            summary_line = lines[-1] if lines else ""
            log.info("MAME verify result: %s", summary_line)
        return result

    def verify_single(self, rom_name: str) -> dict:
        """Verify a single ROM set."""
        if not self.available:
            return {"success": False, "stderr": "MAME not found"}
        return _run([self.exe, "-verifyroms", rom_name], timeout=30)


# ── Igir Integration ────────────────────────────────────────────────

class IgirTool:
    """Wrapper for Igir ROM collection manager."""

    def __init__(self):
        self.exe = _which("igir") or _which("igir.cmd")

    @property
    def available(self) -> bool:
        return self.exe is not None

    def scan_and_report(self, dat_files: str, input_dirs: list[str],
                        output_dir: str) -> dict:
        """Scan ROMs against DAT files and generate a report."""
        if not self.available:
            return {"success": False, "stderr": "Igir not found. Install: npm install -g igir"}

        cmd = [self.exe, "report"]
        cmd.extend(["--dat", dat_files])
        for d in input_dirs:
            cmd.extend(["--input", d])
        cmd.extend(["--output", output_dir])

        result = _run(cmd, timeout=1800)
        if result["success"]:
            audit("igir_report", output_dir)
        return result

    def copy_and_organize(self, dat_files: str, input_dirs: list[str],
                          output_dir: str, zip_output: bool = False) -> dict:
        """Copy and organize ROMs based on DAT files."""
        if not self.available:
            return {"success": False, "stderr": "Igir not found"}

        cmd = [self.exe, "copy"]
        if zip_output:
            cmd.append("zip")
        cmd.extend(["--dat", dat_files])
        for d in input_dirs:
            cmd.extend(["--input", d])
        cmd.extend(["--output", output_dir])

        result = _run(cmd, timeout=7200)  # Can take hours for large sets
        if result["success"]:
            audit("igir_organize", output_dir)
        return result

    def find_missing(self, dat_files: str, input_dirs: list[str],
                     output_dir: str) -> dict:
        """Generate a fixdat of missing ROMs."""
        if not self.available:
            return {"success": False, "stderr": "Igir not found"}

        cmd = [self.exe, "report", "--fixdat"]
        cmd.extend(["--dat", dat_files])
        for d in input_dirs:
            cmd.extend(["--input", d])
        cmd.extend(["--output", output_dir])

        return _run(cmd, timeout=1800)


# ── Flips (ROM Patcher) Integration ─────────────────────────────────

class FlipsTool:
    """Wrapper for Floating IPS (Flips) ROM patcher."""

    def __init__(self):
        self.exe = _which("flips") or _which("flips.exe")

    @property
    def available(self) -> bool:
        return self.exe is not None

    def apply_patch(self, rom_file: str, patch_file: str,
                    output_file: Optional[str] = None) -> dict:
        """Apply an IPS or BPS patch to a ROM."""
        if not self.available:
            return {"success": False, "stderr": "Flips not found"}

        cmd = [self.exe, "--apply", patch_file, rom_file]
        if output_file:
            cmd.append(output_file)

        result = _run(cmd, timeout=60)
        if result["success"]:
            target = output_file or rom_file
            audit("rom_patched", f"{rom_file} + {patch_file} -> {target}")
        return result

    def create_patch(self, original: str, modified: str,
                     patch_file: str, format: str = "bps") -> dict:
        """Create a patch from original and modified ROM files."""
        if not self.available:
            return {"success": False, "stderr": "Flips not found"}

        flag = "--create" if format == "ips" else f"--create-{format}"
        cmd = [self.exe, flag, original, modified, patch_file]
        return _run(cmd, timeout=60)


# ── Skyscraper Integration ──────────────────────────────────────────

class SkyscraperTool:
    """Wrapper for Skyscraper game metadata/artwork scraper."""

    def __init__(self):
        self.exe = _which("Skyscraper") or _which("skyscraper")

    @property
    def available(self) -> bool:
        return self.exe is not None

    def scrape(self, platform: str, input_dir: str,
               scraper: str = "screenscraper") -> dict:
        """Scrape metadata and artwork for a platform."""
        if not self.available:
            return {"success": False, "stderr": "Skyscraper not found"}

        cmd = [self.exe, "-p", platform, "-s", scraper, "-i", input_dir]
        result = _run(cmd, timeout=3600)
        if result["success"]:
            audit("media_scraped", f"{platform} via {scraper}")
        return result

    def generate(self, platform: str, frontend: str = "emulationstation") -> dict:
        """Generate game list and artwork from cached data."""
        if not self.available:
            return {"success": False, "stderr": "Skyscraper not found"}

        cmd = [self.exe, "-p", platform, "-f", frontend]
        return _run(cmd, timeout=600)


# ── Tool Discovery ──────────────────────────────────────────────────

def discover_tools() -> dict:
    """Discover which external tools are installed and available."""
    tools = {}

    # MAME
    mame = MAMETool()
    tools["mame"] = {
        "installed": mame.available,
        "path": mame.exe,
        "version": mame.get_version() if mame.available else None,
    }

    # Igir
    igir = IgirTool()
    tools["igir"] = {
        "installed": igir.available,
        "path": igir.exe,
    }

    # Flips
    flips = FlipsTool()
    tools["flips"] = {
        "installed": flips.available,
        "path": flips.exe,
    }

    # Skyscraper
    sky = SkyscraperTool()
    tools["skyscraper"] = {
        "installed": sky.available,
        "path": sky.exe,
    }

    # Other common tools
    for name in ("7z", "7za", "python", "node", "npm", "git"):
        path = shutil.which(name)
        tools[name] = {"installed": path is not None, "path": path}

    installed_count = sum(1 for t in tools.values() if t["installed"])
    log.info("Discovered %d/%d external tools", installed_count, len(tools))

    return tools
