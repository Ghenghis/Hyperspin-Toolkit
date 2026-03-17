"""HyperSpin Extreme Toolkit — Main CLI Entry Point."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress

from core.config import load_config, get as cfg_get
from core.logger import get_logger, audit
from core import database as db

console = Console()
log = get_logger("main")

BANNER = """
[bold cyan]⚡ HyperSpin Extreme Toolkit v2.0[/bold cyan]
[dim]Full ecosystem management for HyperSpin, RocketLauncher, ROMs & Emulators[/dim]
"""


@click.group()
@click.option("--config", "-c", default=None, help="Path to config.yaml")
def cli(config):
    """HyperSpin Extreme Toolkit — manage your entire arcade collection."""
    load_config(config)
    db.init_db()


# ---- Init / Setup ----

@cli.command()
def init():
    """Initialize the toolkit: discover systems, emulators, and populate database."""
    console.print(BANNER)
    console.print("[bold]Initializing toolkit...[/bold]")

    from engines.scanner import discover_systems, register_systems, discover_emulators, register_emulators

    with Progress() as progress:
        task = progress.add_task("Discovering systems...", total=3)

        systems = discover_systems()
        registered = register_systems(systems)
        progress.update(task, advance=1, description=f"Registered {registered} systems")

        emulators = discover_emulators()
        emu_count = register_emulators(emulators)
        progress.update(task, advance=1, description=f"Registered {emu_count} emulators")

        progress.update(task, advance=1, description="Done!")

    console.print(f"\n[green]✓[/green] {registered} systems registered")
    console.print(f"[green]✓[/green] {emu_count} emulators registered")
    console.print("\n[dim]Run 'python main.py audit' for a full ecosystem audit.[/dim]")


# ---- Audit ----

@cli.group()
def audit_cmd():
    """Audit ROMs, emulators, media, and configs."""
    pass


@audit_cmd.command("full")
def audit_full():
    """Run a full ecosystem audit."""
    console.print(BANNER)
    console.print("[bold]Running full ecosystem audit...[/bold]\n")

    from engines.auditor import run_full_audit
    results = run_full_audit()
    summary = results.get("summary", {})

    table = Table(title="Ecosystem Audit Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Total Systems", str(summary.get("total_systems", 0)))
    table.add_row("Systems with ROMs", str(summary.get("systems_with_roms", 0)))
    table.add_row("Systems with XML DB", str(summary.get("systems_with_xml", 0)))
    table.add_row("Total ROMs", f"{summary.get('total_roms', 0):,}")
    table.add_row("Total Games in XML", f"{summary.get('total_games_in_xml', 0):,}")
    table.add_row("Total Emulators", str(summary.get("total_emulators", 0)))
    table.add_row("Healthy Emulators", str(summary.get("healthy_emulators", 0)))
    table.add_row("Health Score", f"{summary.get('health_score', 0):.1f}%")

    console.print(table)

    # Save report
    output_dir = Path(cfg_get("paths.output_root", ""))
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "latest_audit.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)
    console.print(f"\n[dim]Full report saved to: {report_path}[/dim]")


@audit_cmd.command("system")
@click.argument("system_name")
def audit_system(system_name):
    """Audit a specific system."""
    from engines.auditor import audit_system as do_audit
    result = do_audit(system_name)

    table = Table(title=f"Audit: {system_name}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("ROMs Found", str(result.get("rom_count", 0)))
    table.add_row("Games in XML", str(result.get("xml_game_count", 0)))
    table.add_row("Has XML DB", "Yes" if result.get("has_xml") else "No")
    table.add_row("Matched Games", str(result.get("matched_games", 0)))
    table.add_row("Missing ROMs", str(result.get("missing_roms", 0)))
    table.add_row("Extra ROMs", str(result.get("extra_roms", 0)))
    table.add_row("Health Score", f"{result.get('health_score', 0):.1f}%")

    console.print(table)

    if result.get("issues"):
        console.print("\n[bold]Issues:[/bold]")
        for issue in result["issues"]:
            icon = "⚠️" if issue["severity"] == "warn" else "ℹ️"
            console.print(f"  {icon} {issue['msg']}")


@audit_cmd.command("roms")
@click.option("--dat-dir", default=None, help="Directory containing DAT files (default: config paths.dat_root)")
@click.option("--sha1", is_flag=True, help="Also verify SHA1 hashes (slower)")
@click.option("--json-out", is_flag=True, help="Output raw JSON instead of table")
def audit_roms(dat_dir, sha1, json_out):
    """M8 — Batch ROM verification: verify all systems that have both ROMs and DAT files.

    \b
    Examples:
      audit roms
      audit roms --dat-dir "D:\\Arcade\\DATs"
      audit roms --sha1 --json-out
    """
    from engines.rom_audit import verify_all_systems

    console.print("[bold]Running M8 batch ROM verification...[/bold]\n")
    result = verify_all_systems(dat_dir=dat_dir, use_sha1=sha1)

    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        return

    # Summary panel
    checked = result.get("systems_checked", 0)
    verified = result.get("verified", 0)
    bad = result.get("bad_hash", 0)
    missing = result.get("missing", 0)
    extra = result.get("extra", 0)
    total = verified + bad + missing + extra
    health_color = "green" if bad == 0 and missing == 0 else ("yellow" if bad + missing < 50 else "red")

    console.print(Panel(
        f"Systems Checked: {checked}\n"
        f"Verified:        [green]{verified}[/green]\n"
        f"Bad Hash:        [{'red' if bad else 'green'}]{bad}[/{'red' if bad else 'green'}]\n"
        f"Missing:         [{'red' if missing else 'green'}]{missing}[/{'red' if missing else 'green'}]\n"
        f"Extra:           {extra}\n"
        f"Total ROMs:      {total}",
        title="ROM Verification Summary (M8)",
        border_style=health_color,
    ))

    # Per-system table
    systems = result.get("systems", {})
    if systems:
        table = Table(title="Per-System ROM Verification", show_lines=True)
        table.add_column("System", style="cyan", width=28)
        table.add_column("Verified", justify="right", style="green", width=9)
        table.add_column("Bad", justify="right", width=6)
        table.add_column("Missing", justify="right", width=8)
        table.add_column("Extra", justify="right", width=7)
        table.add_column("Complete %", justify="right", width=10)

        for sys_name, sdata in sorted(systems.items()):
            pct = sdata.get("completeness_pct", 0)
            pct_color = "green" if pct >= 90 else ("yellow" if pct >= 50 else "red")
            bad_str = f"[red]{sdata.get('bad_hash', 0)}[/red]" if sdata.get("bad_hash") else "0"
            miss_str = f"[red]{sdata.get('missing', 0)}[/red]" if sdata.get("missing") else "0"
            table.add_row(
                sys_name[:27],
                str(sdata.get("verified", 0)),
                bad_str, miss_str,
                str(sdata.get("extra", 0)),
                f"[{pct_color}]{pct:.1f}%[/{pct_color}]",
            )

        console.print(table)


@audit_cmd.command("rom-verify")
@click.argument("system_name")
@click.argument("dat_path")
@click.option("--rom-dir", default=None, help="ROM directory (default: auto-detect from HyperSpin root)")
@click.option("--sha1", is_flag=True, help="Also verify SHA1 hashes")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def audit_rom_verify(system_name, dat_path, rom_dir, sha1, json_out):
    """M8 — Verify ROMs for a single system against a DAT file.

    \b
    Examples:
      audit rom-verify MAME "D:\\Arcade\\DATs\\MAME.dat"
      audit rom-verify "Nintendo 64" "D:\\DATs\\n64.dat" --rom-dir "D:\\ROMs\\N64"
      audit rom-verify MAME mame.xml --sha1
    """
    from engines.rom_audit import verify_roms

    if rom_dir is None:
        hs_root = Path(cfg_get("paths.hyperspin_root", ""))
        rom_dir = str(hs_root / system_name)

    console.print(f"[bold]Verifying ROMs: {system_name}[/bold]")
    console.print(f"  ROM dir: {rom_dir}")
    console.print(f"  DAT:     {dat_path}\n")

    result = verify_roms(rom_dir, dat_path, use_sha1=sha1, system_name=system_name)

    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        return

    table = Table(title=f"ROM Verification: {system_name}", show_lines=True)
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Value", width=14)
    table.add_row("Games in DAT", str(result.get("total_in_dat", 0)))
    table.add_row("ROMs in DAT", str(result.get("total_roms_in_dat", 0)))
    table.add_row("Verified", f"[green]{result.get('verified', 0)}[/green]")
    table.add_row("Bad Hash", f"[{'red' if result.get('bad_hash') else 'green'}]{result.get('bad_hash', 0)}[/{'red' if result.get('bad_hash') else 'green'}]")
    table.add_row("Missing", f"[{'red' if result.get('missing') else 'green'}]{result.get('missing', 0)}[/{'red' if result.get('missing') else 'green'}]")
    table.add_row("Extra", str(result.get("extra", 0)))
    table.add_row("Completeness", f"{result.get('completeness_pct', 0):.1f}%")
    console.print(table)

    # Show bad hashes and missing (top 10 each)
    details = result.get("results", [])
    bad_items = [r for r in details if r.get("status") == "bad_hash"]
    if bad_items:
        console.print(f"\n[bold red]Bad Hashes ({len(bad_items)}):[/bold red]")
        for item in bad_items[:10]:
            console.print(f"  [red]{item['game_name']}/{item['rom_name']}[/red] — {item.get('detail', '')}")
        if len(bad_items) > 10:
            console.print(f"  [dim]... and {len(bad_items) - 10} more[/dim]")


@audit_cmd.command("media")
@click.option("--no-corruption", is_flag=True, help="Skip corruption checks (faster)")
@click.option("--no-orphans", is_flag=True, help="Skip orphan detection")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def audit_media(no_corruption, no_orphans, json_out):
    """M9 — Batch media audit: check wheel, video, theme, artwork coverage for all systems.

    \b
    Examples:
      audit media
      audit media --no-corruption
      audit media --json-out
    """
    from engines.media_auditor import audit_all_media

    console.print("[bold]Running M9 batch media audit...[/bold]\n")
    result = audit_all_media(
        check_corruption=not no_corruption,
        check_orphans=not no_orphans,
    )

    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        return

    checked = result.get("systems_checked", 0)
    avg_cov = result.get("avg_coverage_pct", 0)
    cov_color = "green" if avg_cov >= 80 else ("yellow" if avg_cov >= 50 else "red")

    console.print(Panel(
        f"Systems Checked:  {checked}\n"
        f"Avg Coverage:     [{cov_color}]{avg_cov:.1f}%[/{cov_color}]\n"
        f"Total Missing:    {result.get('total_missing', 0)}\n"
        f"Total Corrupt:    {result.get('total_corrupt', 0)}\n"
        f"Total Orphaned:   {result.get('total_orphaned', 0)}\n"
        f"Total Oversized:  {result.get('total_oversized', 0)}",
        title="Media Audit Summary (M9)",
        border_style=cov_color,
    ))

    worst = result.get("worst_systems", [])
    if worst:
        table = Table(title="Lowest Coverage Systems", show_lines=False)
        table.add_column("System", style="cyan", width=30)
        table.add_column("Coverage %", justify="right", width=12)
        for w in worst:
            c = w["coverage_pct"]
            cc = "green" if c >= 80 else ("yellow" if c >= 50 else "red")
            table.add_row(w["name"][:29], f"[{cc}]{c:.1f}%[/{cc}]")
        console.print(table)


@audit_cmd.command("media-system")
@click.argument("system_name")
@click.option("--no-corruption", is_flag=True, help="Skip corruption checks")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def audit_media_system(system_name, no_corruption, json_out):
    """M9 — Media audit for a single system: wheel, video, theme, artwork coverage.

    \b
    Examples:
      audit media-system MAME
      audit media-system "Nintendo 64" --json-out
    """
    from engines.media_auditor import audit_media_for_system

    console.print(f"[bold]Media audit: {system_name}[/bold]\n")
    result = audit_media_for_system(
        system_name,
        check_corruption=not no_corruption,
    )

    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        return

    cov = result.get("overall_coverage_pct", 0)
    cov_color = "green" if cov >= 80 else ("yellow" if cov >= 50 else "red")

    console.print(Panel(
        f"Games in XML:     {result.get('game_count', 0)}\n"
        f"Overall Coverage: [{cov_color}]{cov:.1f}%[/{cov_color}]\n"
        f"Missing:          {result['summary']['total_missing']}\n"
        f"Corrupt:          {result['summary']['total_corrupt']}\n"
        f"Orphaned:         {result['summary']['total_orphaned']}",
        title=f"Media Audit: {system_name} (M9)",
        border_style=cov_color,
    ))

    table = Table(title="Per-Type Coverage", show_lines=True)
    table.add_column("Media Type", style="cyan", width=14)
    table.add_column("Files", justify="right", width=7)
    table.add_column("Coverage", justify="right", width=10)
    table.add_column("Missing", justify="right", width=8)
    table.add_column("Corrupt", justify="right", width=8)
    table.add_column("Orphaned", justify="right", width=8)

    for mtype, mdata in result.get("media_types", {}).items():
        mc = mdata.get("coverage_pct", 0)
        mcc = "green" if mc >= 80 else ("yellow" if mc >= 50 else "red")
        table.add_row(
            mtype,
            str(mdata.get("total_files", 0)),
            f"[{mcc}]{mc:.1f}%[/{mcc}]",
            str(mdata.get("missing_count", 0)),
            str(mdata.get("corrupt_count", 0)),
            str(mdata.get("orphaned_count", 0)),
        )
    console.print(table)


@audit_cmd.command("emulators")
def audit_emulators():
    """Audit all emulators."""
    from engines.auditor import audit_emulators as do_audit
    results = do_audit()

    table = Table(title="Emulator Audit")
    table.add_column("Emulator", style="cyan")
    table.add_column("EXEs", justify="right")
    table.add_column("Files", justify="right")
    table.add_column("Size MB", justify="right")
    table.add_column("Healthy", style="green")

    for emu in results[:50]:
        healthy = "[green]Yes[/green]" if emu.get("is_healthy") else "[red]No[/red]"
        table.add_row(
            emu["name"],
            str(emu.get("exe_count", 0)),
            str(emu.get("file_count", 0)),
            f"{emu.get('total_size_mb', 0):.1f}",
            healthy,
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(results)} emulators[/dim]")


@audit_cmd.command("emulators-health")
@click.option("--emu-root", default=None, help="Path to emulators root directory")
@click.option("--rl-root", default=None, help="Path to RocketLauncher root directory")
@click.option("--json-out", is_flag=True, help="Output raw JSON instead of table")
def audit_emulators_health(emu_root, rl_root, json_out):
    """M7 — Deep emulator health check: verify EXEs, versions, INI configs, RL modules.

    \b
    Examples:
      audit emulators-health
      audit emulators-health --emu-root "D:\\Arcade\\Emulators"
      audit emulators-health --emu-root "D:\\Arcade\\Emulators" --rl-root "D:\\Arcade\\RocketLauncher"
    """
    from engines.emulator_health import health_summary

    console.print("[bold]Running M7 emulator health check...[/bold]\n")
    summary = health_summary(emu_root=emu_root, rl_root=rl_root)

    if json_out:
        console.print_json(json.dumps(summary, indent=2))
        return

    # Summary panel
    total     = summary["total"]
    healthy   = summary["healthy"]
    unhealthy = summary["unhealthy"]
    avg       = summary["avg_health_score"]
    health_color = "green" if healthy / max(total, 1) >= 0.8 else ("yellow" if healthy / max(total, 1) >= 0.5 else "red")

    console.print(Panel(
        f"Total Emulators:  {total}\n"
        f"Healthy:          [{health_color}]{healthy}[/{health_color}]\n"
        f"Needs Attention:  [{'red' if unhealthy else 'green'}]{unhealthy}[/{'red' if unhealthy else 'green'}]\n"
        f"Avg Health Score: {avg:.1f} / 100",
        title="Emulator Ecosystem Health (M7)",
        border_style=health_color,
    ))

    # Per-emulator table
    table = Table(title="Emulator Health Details", show_lines=True)
    table.add_column("Emulator", style="cyan", width=28)
    table.add_column("Score", justify="right", width=7)
    table.add_column("EXE", width=5)
    table.add_column("Version", width=14)
    table.add_column("RL Module", width=9)
    table.add_column("CFG Issues", justify="right", width=10)
    table.add_column("Healthy", width=8)

    for emu in summary["emulators"]:
        score_color = "green" if emu["health_score"] >= 70 else ("yellow" if emu["health_score"] >= 40 else "red")
        exe_icon = "[green]✓[/green]" if emu["exe_exists"] else "[red]✗[/red]"
        rl_icon  = "[green]✓[/green]" if emu["rl_module_exists"] else "[dim]—[/dim]"
        healthy_str = "[green]YES[/green]" if emu["is_healthy"] else "[red]NO[/red]"
        cfg_issues = str(len(emu["config_issues"])) if emu["config_issues"] else "[green]0[/green]"

        table.add_row(
            emu["name"][:27],
            f"[{score_color}]{emu['health_score']:.0f}[/{score_color}]",
            exe_icon,
            emu["version"][:13],
            rl_icon,
            cfg_issues,
            healthy_str,
        )

    console.print(table)

    if summary["critical_issues"]:
        console.print(f"\n[bold red]Critical Issues ({len(summary['critical_issues'])}):[/bold red]")
        for item in summary["critical_issues"][:10]:
            console.print(f"  [bold]{item['emulator']}[/bold]")
            for issue in item["issues"][:3]:
                sev = issue.get("severity", "warn")
                color = "red" if sev == "error" else ("yellow" if sev == "warn" else "dim")
                console.print(f"    [{color}]• {issue['msg'][:100]}[/{color}]")


@audit_cmd.command("emulator")
@click.argument("name_or_path")
@click.option("--rl-root", default=None, help="Path to RocketLauncher root")
def audit_single_emulator(name_or_path, rl_root):
    """M7 — Deep health check for a single emulator by name or path.

    \b
    Examples:
      audit emulator MAME
      audit emulator "D:\\Arcade\\Emulators\\RetroArch"
    """
    from engines.emulator_health import check_single_emulator

    console.print(f"[bold]Checking emulator: {name_or_path}[/bold]\n")
    result = check_single_emulator(name_or_path)

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        return

    score_color = "green" if result["health_score"] >= 70 else ("yellow" if result["health_score"] >= 40 else "red")

    table = Table(title=f"Emulator: {result['name']}", show_lines=True)
    table.add_column("Field", style="cyan", width=18)
    table.add_column("Value")
    table.add_row("Path",          result["path"])
    table.add_row("Executable",    result["exe_path"] or "[red]NOT FOUND[/red]")
    table.add_row("EXE Size",      f"{result['exe_size_bytes']:,} bytes" if result["exe_size_bytes"] else "—")
    table.add_row("Version",       result["version"])
    table.add_row("Health Score",  f"[{score_color}]{result['health_score']:.0f} / 100[/{score_color}]")
    table.add_row("Healthy",       "[green]YES[/green]" if result["is_healthy"] else "[red]NO[/red]")
    table.add_row("Config Files",  str(len(result["config_files"])))
    table.add_row("Config Issues", str(len(result["config_issues"])) or "[green]none[/green]")
    table.add_row("RL Module",     result["rl_module_path"] or "[dim]not found[/dim]")
    console.print(table)

    if result["issues"]:
        console.print("\n[bold]Issues:[/bold]")
        for issue in result["issues"]:
            sev = issue.get("severity", "warn")
            color = "red" if sev == "error" else ("yellow" if sev == "warn" else "dim")
            console.print(f"  [{color}]• {issue['msg']}[/{color}]")


# ---- Backup ----

@cli.group()
def backup():
    """Backup and recovery operations."""
    pass


@backup.command("create")
@click.argument("source")
@click.option("--label", "-l", default="manual", help="Backup label")
@click.option("--type", "-t", "btype", default="full", type=click.Choice(["full", "incremental"]))
def backup_create(source, label, btype):
    """Create a backup of a directory."""
    from engines.backup import create_backup
    console.print(f"[bold]Creating {btype} backup of {source}...[/bold]")
    result = create_backup(source, label=label, backup_type=btype)
    console.print(f"[green]✓[/green] Backup created: {result['file_count']:,} files, "
                  f"{result['total_size_bytes']:,} bytes")
    console.print(f"[dim]Location: {result.get('archive_path')}[/dim]")


@backup.command("list")
def backup_list():
    """List all backups."""
    rows = db.execute("SELECT * FROM backups ORDER BY created_at DESC LIMIT 20")
    if not rows:
        console.print("[dim]No backups found.[/dim]")
        return

    table = Table(title="Backup History")
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Target")
    table.add_column("Files", justify="right")
    table.add_column("Size MB", justify="right")
    table.add_column("Status")
    table.add_column("Created")

    for r in rows:
        size_mb = f"{(r['size_bytes'] or 0) / (1024*1024):.1f}"
        table.add_row(
            str(r["id"]), r["backup_type"], r["target"],
            str(r["file_count"] or 0), size_mb, r["status"], r["created_at"],
        )
    console.print(table)


@backup.command("restore")
@click.argument("backup_dir")
@click.argument("target")
@click.option("--dry-run", is_flag=True, help="Preview without restoring")
def backup_restore(backup_dir, target, dry_run):
    """Restore files from a backup."""
    from engines.backup import restore_from_backup
    result = restore_from_backup(backup_dir, target, dry_run=dry_run)
    label = "(dry run)" if dry_run else ""
    console.print(f"[green]✓[/green] Restored {result['restored']} files {label}")


@backup.command("rollback")
@click.argument("backup_id")
@click.option("--dry-run", is_flag=True, help="Preview without restoring")
def backup_rollback(backup_id, dry_run):
    """Rollback to a specific backup by ID (from 'backup list')."""
    from engines.backup import restore_from_backup
    from core import database as db

    rows = db.execute("SELECT * FROM backups WHERE id=?", (backup_id,))
    if not rows:
        console.print(f"[red]Backup ID {backup_id} not found. Run 'backup list' to see IDs.[/red]")
        return

    backup_row = rows[0]
    archive_path = backup_row.get("archive_path") or backup_row.get("target", "")
    original_target = backup_row.get("target", "")

    console.print(f"[bold]Rolling back backup {backup_id}:[/bold]")
    console.print(f"  Source: {archive_path}")
    console.print(f"  Target: {original_target}")

    if dry_run:
        console.print("[dim](dry run — no files changed)[/dim]")
        return

    if not click.confirm(f"Overwrite {original_target} with backup {backup_id}?"):
        console.print("[dim]Rollback cancelled.[/dim]")
        return

    result = restore_from_backup(archive_path, original_target, dry_run=False)
    console.print(f"[green]✓[/green] Rollback complete — {result['restored']} files restored")


# ---- M10 XML Tools ----

@cli.group("xml")
def xml_cmd():
    """M10 — HyperSpin XML database tools: validate, merge, rebuild, filter, sort, stats."""
    pass


@xml_cmd.command("validate")
@click.argument("xml_path")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def xml_validate(xml_path, json_out):
    """M10 — Validate a HyperSpin XML database file.

    \b
    Examples:
      xml validate "D:\\Arcade\\Databases\\MAME\\MAME.xml"
    """
    from engines.xml_tools import validate_xml

    result = validate_xml(xml_path)

    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return

    valid_str = "[green]VALID[/green]" if result["valid"] else "[red]INVALID[/red]"
    console.print(f"  Status:     {valid_str}")
    console.print(f"  Games:      {result['game_count']}")
    console.print(f"  Duplicates: {len(result.get('duplicates', []))}")

    for issue in result.get("issues", []):
        icon = {"error": "[red]✗[/red]", "warn": "[yellow]⚠[/yellow]", "info": "[dim]ℹ[/dim]"}.get(issue["severity"], "•")
        console.print(f"  {icon} {issue['detail']}")


@xml_cmd.command("merge")
@click.argument("xml_files", nargs=-1, required=True)
@click.option("--output", "-o", required=True, help="Output XML file path")
@click.option("--no-dedup", is_flag=True, help="Keep duplicate game names")
@click.option("--no-sort", is_flag=True, help="Don't sort alphabetically")
def xml_merge(xml_files, output, no_dedup, no_sort):
    """M10 — Merge multiple HyperSpin XML databases into one.

    \b
    Examples:
      xml merge a.xml b.xml c.xml -o merged.xml
      xml merge *.xml -o combined.xml --no-dedup
    """
    from engines.xml_tools import merge_xml

    console.print(f"[bold]Merging {len(xml_files)} XML files...[/bold]")
    result = merge_xml(list(xml_files), output, dedup=not no_dedup, sort=not no_sort)

    console.print(f"[green]✓[/green] Merged: {result['merged_count']} games")
    console.print(f"  Input total: {result['total_input']}")
    console.print(f"  Dupes removed: {result['duplicates_removed']}")
    console.print(f"  Output: {result['output_path']}")


@xml_cmd.command("rebuild")
@click.argument("rom_dir")
@click.argument("output")
@click.option("--reference", "-r", default=None, help="Reference XML for metadata")
@click.option("--system", "-s", default="", help="System name for header")
def xml_rebuild(rom_dir, output, reference, system):
    """M10 — Rebuild a HyperSpin XML database from a ROM directory.

    \b
    Examples:
      xml rebuild "D:\\ROMs\\MAME" "D:\\Databases\\MAME\\MAME.xml" -s MAME
      xml rebuild "D:\\ROMs\\N64" out.xml -r old_n64.xml
    """
    from engines.xml_tools import rebuild_xml

    console.print(f"[bold]Rebuilding XML from {rom_dir}...[/bold]")
    result = rebuild_xml(rom_dir, output, reference_xml=reference, system_name=system)

    console.print(f"[green]✓[/green] Rebuilt: {result['rom_count']} ROMs")
    console.print(f"  With metadata:    {result['with_metadata']}")
    console.print(f"  Without metadata: {result['without_metadata']}")
    console.print(f"  Output: {result['output_path']}")


@xml_cmd.command("filter")
@click.argument("xml_path")
@click.argument("rom_dir")
@click.option("--output", "-o", default=None, help="Output path (default: overwrite source)")
def xml_filter(xml_path, rom_dir, output):
    """M10 — Filter XML to only games with ROMs present in directory.

    \b
    Examples:
      xml filter MAME.xml "D:\\ROMs\\MAME"
      xml filter MAME.xml "D:\\ROMs\\MAME" -o filtered.xml
    """
    from engines.xml_tools import filter_xml

    console.print(f"[bold]Filtering {xml_path} against {rom_dir}...[/bold]")
    result = filter_xml(xml_path, rom_dir, output)

    console.print(f"[green]✓[/green] Filtered: {result['original_count']} → {result['filtered_count']} games")
    console.print(f"  Removed: {result['removed_count']}")
    console.print(f"  Output:  {result['output_path']}")


@xml_cmd.command("sort")
@click.argument("xml_path")
@click.option("--output", "-o", default=None, help="Output path (default: overwrite source)")
def xml_sort(xml_path, output):
    """M10 — Sort games alphabetically in a HyperSpin XML.

    \b
    Examples:
      xml sort MAME.xml
      xml sort MAME.xml -o sorted.xml
    """
    from engines.xml_tools import sort_xml

    result = sort_xml(xml_path, output)
    console.print(f"[green]✓[/green] Sorted {result['game_count']} games → {result['output_path']}")


@xml_cmd.command("stats")
@click.argument("xml_path")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def xml_stats(xml_path, json_out):
    """M10 — Show statistics for a HyperSpin XML database.

    \b
    Examples:
      xml stats "D:\\Arcade\\Databases\\MAME\\MAME.xml"
    """
    from engines.xml_tools import stats_xml

    result = stats_xml(xml_path)

    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        return

    console.print(f"  Games: {result['game_count']}")
    console.print(f"  Header: {'Yes' if result['has_header'] else 'No'}")

    yr = result.get("year_range")
    if yr:
        console.print(f"  Years: {yr['min']} – {yr['max']}")

    mfg = result.get("top_manufacturers", [])
    if mfg:
        console.print(f"  Top Manufacturers: {', '.join(m['name'] + f' ({m[\"count\"]})' for m in mfg[:5])}")

    genres = result.get("top_genres", [])
    if genres:
        console.print(f"  Top Genres: {', '.join(g['name'] + f' ({g[\"count\"]})' for g in genres[:5])}")

    fc = result.get("field_completeness", {})
    if fc:
        console.print("  Field Completeness:")
        for f, pct in fc.items():
            bar_color = "green" if pct >= 80 else ("yellow" if pct >= 50 else "red")
            console.print(f"    {f:15s} [{bar_color}]{pct:.1f}%[/{bar_color}]")


# ---- Update ----

@cli.group()
def update():
    """Safe program update pipeline."""
    pass


@update.command("register")
@click.argument("program_name")
@click.argument("target_path")
@click.option("--old-version", default="")
@click.option("--new-version", default="")
@click.option("--notes", default="")
def update_register(program_name, target_path, old_version, new_version, notes):
    """Register an update in the queue."""
    from engines.update_manager import UpdatePipeline
    pipeline = UpdatePipeline(program_name, target_path)
    uid = pipeline.register(old_version, new_version, notes)
    console.print(f"[green]✓[/green] Update registered: {program_name} (id={uid})")


@update.command("queue")
def update_queue():
    """Show pending updates."""
    from engines.update_manager import get_update_queue
    queue = get_update_queue()
    if not queue:
        console.print("[dim]No pending updates.[/dim]")
        return
    for item in queue:
        console.print(f"  [{item['id']}] {item['program_name']} — {item['status']}")


@update.command("history")
def update_history():
    """Show update history."""
    from engines.update_manager import get_update_history
    history = get_update_history()
    if not history:
        console.print("[dim]No update history.[/dim]")
        return

    table = Table(title="Update History")
    table.add_column("ID")
    table.add_column("Program")
    table.add_column("Old Ver")
    table.add_column("New Ver")
    table.add_column("Status")
    table.add_column("Created")

    for h in history:
        table.add_row(
            str(h["id"]), h["program_name"], h.get("old_version", ""),
            h.get("new_version", ""), h["status"], h["created_at"],
        )
    console.print(table)


# ---- AI ----

@cli.group()
def ai():
    """AI assistant commands."""
    pass


@ai.command("status")
def ai_status():
    """Check AI provider status."""
    from engines.ai_engine import get_ai
    engine = get_ai()
    status = engine.detect_available()

    table = Table(title="AI Provider Status")
    table.add_column("Provider", style="cyan")
    table.add_column("Status")
    table.add_column("URL")

    for name, available in status.items():
        p = engine.providers.get(name)
        s = "[green]Online[/green]" if available else "[red]Offline[/red]"
        url = p.base_url if p else ""
        table.add_row(name, s, url)
    console.print(table)


@ai.command("ask")
@click.argument("question")
def ai_ask(question):
    """Ask the AI assistant a question."""
    from engines.ai_engine import get_ai
    engine = get_ai()
    try:
        answer = engine.ask(question)
        console.print(Panel(answer, title="AI Response", border_style="blue"))
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        console.print("[dim]Make sure Ollama, LM Studio, or vLLM is running.[/dim]")


@ai.command("query")
@click.argument("question")
def ai_query(question):
    """Query the database using natural language."""
    from engines.ai_engine import get_nl_query
    nlq = get_nl_query()
    try:
        result = nlq.query(question)
        if result.get("error"):
            console.print(f"[red]Error: {result['error']}[/red]")
            return
        console.print(f"[dim]SQL: {result.get('generated_sql')}[/dim]")
        console.print(f"[dim]Rows: {result.get('row_count', 0)}[/dim]\n")
        console.print(Panel(result.get("explanation", ""), title="Answer", border_style="green"))
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


@ai.command("analyse")
@click.option("--last-audit", "use_last", is_flag=True, help="Analyse the most recent audit report")
@click.option("--audit-file", default=None, help="Path to a specific audit JSON file")
@click.option("--focus", default=None, help="Focus area: emulators, roms, media, space, updates")
def ai_analyse(use_last, audit_file, focus):
    """Analyse audit results with the local LLM to generate recommendations."""
    output_dir = Path(cfg_get("paths.output_root", ""))
    if use_last or not audit_file:
        audit_path = output_dir / "latest_audit.json"
    else:
        audit_path = Path(audit_file)

    if not audit_path.exists():
        console.print(f"[red]Audit file not found: {audit_path}[/red]")
        console.print("[dim]Run 'python main.py audit full' first.[/dim]")
        return

    with open(audit_path, encoding="utf-8") as fh:
        audit_data = json.load(fh)

    summary = audit_data.get("summary", {})
    health = summary.get("health_score", 0)
    issues_count = sum(len(s.get("issues", [])) for s in audit_data.get("systems", []))

    focus_note = f" Focus on: {focus}." if focus else ""
    question = (
        f"I have a HyperSpin arcade collection audit result. Health score: {health:.1f}%. "
        f"Total issues found: {issues_count}.{focus_note} "
        f"Key metrics: {json.dumps(summary, default=str)[:2000]}. "
        f"What are the top 5 specific actions I should take to improve my collection?"
    )

    from engines.ai_engine import get_ai
    engine = get_ai()
    try:
        answer = engine.ask(question)
        console.print(Panel(answer, title=f"AI Analysis (health={health:.1f}%)", border_style="blue"))
        console.print(f"[dim]Analysed: {audit_path}[/dim]")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        console.print("[dim]Make sure LM Studio or Ollama is running.[/dim]")


@ai.command("recommend")
@click.option("--task", "-t", default="agentic",
              type=click.Choice(["agentic", "coding", "reasoning", "vision", "fast", "general"]),
              help="AI task to recommend a model for")
@click.option("--provider", "-p", default="any",
              type=click.Choice(["lmstudio", "ollama", "any"]),
              help="Restrict to a specific provider")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def ai_recommend(task, provider, json_out):
    """M17 — Recommend the best local LLM model for a given task."""
    from engines.nl_query import recommend_model_for_task
    console.print(f"[bold]Finding best model for '{task}' task...[/bold]\n")
    result = recommend_model_for_task(task, provider)
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    if result.get("error"):
        console.print(f"[red]Error: {result['error']}[/red]")
        return
    table = Table(title=f"Recommended Model for '{task}'")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Name", result.get("name", ""))
    table.add_row("Model ID", result.get("model_id", ""))
    table.add_row("Provider", result.get("provider", ""))
    table.add_row("Family", result.get("family", ""))
    table.add_row("Size", f"{result.get('size_gb', 0):.1f} GB")
    table.add_row("Quantization", result.get("quant", ""))
    table.add_row("Fits VRAM", "[green]Yes[/green]" if result.get("fits_vram") else "[red]No[/red]")
    table.add_row("Context", str(result.get("context_native", "")))
    table.add_row("Tags", ", ".join(result.get("tags", [])))
    console.print(table)


@ai.command("report")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def ai_report(json_out):
    """M17 — Generate a comprehensive AI/LLM status report with recommendations."""
    from engines.nl_query import full_ai_report
    console.print("[bold]Generating AI/LLM report...[/bold]\n")
    report = full_ai_report()
    if json_out:
        console.print_json(json.dumps(report, indent=2, default=str))
        return
    if report.get("error"):
        console.print(f"[red]Error: {report['error']}[/red]")
        return
    for prov in ("lmstudio", "ollama"):
        info = report.get(prov, {})
        running = info.get("running", False)
        icon = "[green]●[/green]" if running else "[red]○[/red]"
        console.print(f"  {icon} [bold]{prov}[/bold]  Models: {info.get('total_models', 0)}")
    recs = report.get("recommendations", {})
    if recs:
        console.print("\n[bold]Per-Task Recommendations:[/bold]")
        for task_name, rec in recs.items():
            model_name = rec.get("name", "none") if isinstance(rec, dict) else str(rec)
            console.print(f"  {task_name}: [cyan]{model_name}[/cyan]")


@ai.command("models")
@click.option("--provider", "-p", default=None,
              type=click.Choice(["lmstudio", "ollama", "huggingface", "all"]),
              help="Restrict to a specific provider (default: all)")
@click.option("--family", "-f", default=None, help="Filter by model family (e.g. llama, mistral)")
@click.option("--vision", is_flag=True, help="Show only vision-capable models")
@click.option("--coder", is_flag=True, help="Show only coding-specialized models")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def ai_models(provider, family, vision, coder, json_out):
    """M16 — Discover and list local LLM models across LM Studio, Ollama, and HuggingFace.

    \b
    Examples:
      ai models
      ai models --provider lmstudio
      ai models --family llama --vision
      ai models --coder
    """
    from engines.llm_detector import scan_lmstudio_models, scan_ollama_models

    console.print("[bold]Scanning for local LLM models...[/bold]\n")
    all_models = []

    providers = [provider] if provider and provider != "all" else ["lmstudio", "ollama"]
    for prov in providers:
        try:
            if prov == "lmstudio":
                models = scan_lmstudio_models()
            elif prov == "ollama":
                models = scan_ollama_models()
            else:
                models = []
            for m in models:
                m_dict = m if isinstance(m, dict) else m.__dict__
                m_dict["provider"] = prov
                all_models.append(m_dict)
        except Exception as exc:
            console.print(f"[dim]{prov}: {exc}[/dim]")

    # Apply filters
    if family:
        all_models = [m for m in all_models if family.lower() in (m.get("family") or "").lower()]
    if vision:
        all_models = [m for m in all_models if m.get("vision")]
    if coder:
        all_models = [m for m in all_models if m.get("coder")]

    if json_out:
        console.print_json(json.dumps(all_models, indent=2, default=str))
        return

    if not all_models:
        console.print("[dim]No models found. Make sure LM Studio or Ollama is running.[/dim]")
        return

    table = Table(title=f"Local LLM Models ({len(all_models)} found)", show_lines=False)
    table.add_column("Provider", style="cyan", width=10)
    table.add_column("Model", width=40)
    table.add_column("Family", width=12)
    table.add_column("Quant", width=8)
    table.add_column("Ctx", justify="right", width=8)
    table.add_column("Size", justify="right", width=9)
    table.add_column("Vision", width=6)
    table.add_column("Coder", width=6)

    for m in all_models:
        ctx = m.get("context_length") or 0
        ctx_str = f"{ctx//1000}K" if ctx >= 1000 else (str(ctx) if ctx else "?")
        size_gb = m.get("size_gb") or 0
        size_str = f"{size_gb:.1f}G" if size_gb else "?"
        vis  = "[green]✓[/green]" if m.get("vision") else ""
        code = "[cyan]✓[/cyan]" if m.get("coder") else ""
        table.add_row(
            m.get("provider", ""),
            (m.get("name") or m.get("id") or "")[:39],
            (m.get("family") or "")[:11],
            (m.get("quantization") or "")[:7],
            ctx_str,
            size_str,
            vis, code,
        )

    console.print(table)
    vision_count = sum(1 for m in all_models if m.get("vision"))
    coder_count  = sum(1 for m in all_models if m.get("coder"))
    console.print(f"[dim]{len(all_models)} models total  |  {vision_count} vision  |  {coder_count} coder-specialized[/dim]")


@ai.command("llm-status")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def ai_llm_status(json_out):
    """M16 — Check LLM provider connectivity and list available models summary.

    \b
    Examples:
      ai llm-status
      ai llm-status --json-out
    """
    from engines.llm_detector import scan_lmstudio_models, scan_ollama_models
    import httpx

    console.print("[bold]Checking LLM provider status...[/bold]\n")

    lmstudio_url  = cfg_get("ai.lmstudio.base_url", None) or cfg_get("ai.lmstudio_url",  "http://localhost:1234")
    ollama_url    = cfg_get("ai.ollama.base_url",   None) or cfg_get("ai.ollama_url",     "http://localhost:11434")
    # Strip /v1 suffix for base connectivity check
    lmstudio_base = lmstudio_url.rstrip("/").removesuffix("/v1")

    status: dict = {}

    for name, base_url, health_path in [
        ("lmstudio", lmstudio_base, "/v1/models"),
        ("ollama",   ollama_url,    "/api/tags"),
    ]:
        try:
            resp = httpx.get(f"{base_url}{health_path}", timeout=3.0)
            online = resp.status_code == 200
        except Exception:
            online = False

        if name == "lmstudio":
            try:
                models = scan_lmstudio_models() if online else []
            except Exception:
                models = []
        else:
            try:
                models = scan_ollama_models() if online else []
            except Exception:
                models = []

        model_list = [m if isinstance(m, dict) else m.__dict__ for m in models]
        status[name] = {
            "online": online,
            "url":    base_url,
            "model_count": len(model_list),
            "models": [m.get("name") or m.get("id") or "" for m in model_list[:10]],
        }

    if json_out:
        console.print_json(json.dumps(status, indent=2, default=str))
        return

    for prov, info in status.items():
        icon  = "[green]●[/green]" if info["online"] else "[red]○[/red]"
        state = "[green]ONLINE[/green]" if info["online"] else "[red]OFFLINE[/red]"
        console.print(f"  {icon}  [bold]{prov}[/bold]  {state}  {info['url']}")
        if info["online"] and info["models"]:
            console.print(f"     Models: {info['model_count']}  "
                          f"([dim]{', '.join(info['models'][:3])}{'...' if info['model_count'] > 3 else ''}[/dim])")
        elif info["online"]:
            console.print(f"     [dim]No models loaded[/dim]")

    total = sum(v["model_count"] for v in status.values())
    console.print(f"\n[dim]Total models available: {total}[/dim]")


@ai.command("vision")
@click.argument("path")
@click.option("--model", default=None, help="Override vision model (default: GLM-4.6V-Flash)")
@click.option("--batch", is_flag=True, help="Analyse all images in the directory")
@click.option("--save", is_flag=True, help="Save analysis to output directory")
def ai_vision(path, model, batch, save):
    """Analyse an image or directory of images with the local vision model (GLM-4.6V-Flash)."""
    import base64
    target = Path(path)
    if not target.exists():
        console.print(f"[red]Path not found: {path}[/red]")
        return

    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
    if target.is_dir():
        if not batch:
            console.print(f"[yellow]{path} is a directory. Use --batch to analyse all images.[/yellow]")
            return
        images = [f for f in target.iterdir() if f.suffix.lower() in image_extensions]
        if not images:
            console.print(f"[red]No images found in {path}[/red]")
            return
        console.print(f"[bold]Analysing {len(images)} images in {path}...[/bold]\n")
    else:
        images = [target]

    try:
        import httpx
        lmstudio_url = cfg_get("ai.lmstudio_url", "http://localhost:1234/v1")
        vision_model = model or cfg_get("ai.vision_model", "lmstudio-community/GLM-4.6V-Flash-GGUF/GLM-4.6V-Flash-Q8_0.gguf")
    except Exception as exc:
        console.print(f"[red]Vision requires httpx: pip install httpx[/red]")
        return

    results = []
    for img_path in images[:20]:  # cap at 20 for batch
        try:
            img_b64 = base64.b64encode(img_path.read_bytes()).decode()
            suffix = img_path.suffix.lower().lstrip(".")
            mime = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"

            payload = {
                "model": vision_model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                        {"type": "text", "text": "Describe this arcade game media image. Rate quality 1-10, note any issues (wrong orientation, low resolution, wrong aspect ratio, artifacts). State whether it is suitable for HyperSpin display."},
                    ],
                }],
                "max_tokens": 512,
                "temperature": 0.1,
            }
            import httpx as _httpx
            resp = _httpx.post(f"{lmstudio_url}/chat/completions", json=payload,
                               headers={"Authorization": "Bearer lm-studio"}, timeout=60.0)
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"]
                console.print(Panel(text, title=f"{img_path.name}", border_style="cyan"))
                results.append({"file": str(img_path), "analysis": text})
            else:
                console.print(f"[red]{img_path.name}: API error {resp.status_code}[/red]")
        except Exception as exc:
            console.print(f"[red]{img_path.name}: {exc}[/red]")

    if save and results:
        output_dir = Path(cfg_get("paths.output_root", ""))
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "vision_analysis.json"
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        console.print(f"[dim]Vision analysis saved to: {out_file}[/dim]")


# ---- Dashboard ----

@cli.command()
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
def dashboard(host, port):
    """Launch the web dashboard."""
    import uvicorn
    h = host or cfg_get("dashboard.host", "127.0.0.1")
    p = port or cfg_get("dashboard.port", 8888)
    console.print(BANNER)
    console.print(f"[bold]Starting dashboard at http://{h}:{p}[/bold]")
    uvicorn.run("dashboard.app:app", host=h, port=int(p), reload=False)


# ---- Agent ----

@cli.group()
def agent():
    """Run AI agents."""
    pass


@agent.command("list")
def agent_list():
    """List available agents."""
    from agents.base_agent import list_agents
    agents = list_agents()
    table = Table(title="Available Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Role")
    table.add_column("Description")
    for a in agents:
        table.add_row(a["name"], a["role"], a["description"])
    console.print(table)


@agent.command("run")
@click.argument("agent_name")
@click.argument("task")
@click.option("--params", "-p", default="{}", help="JSON params")
def agent_run(agent_name, task, params):
    """Run an agent task."""
    from agents.base_agent import get_agent
    try:
        agent_instance = get_agent(agent_name)
        parsed_params = json.loads(params)
        result = agent_instance.run(task, parsed_params)
        if result.success:
            console.print(f"[green]✓[/green] {result.agent_name}: {result.task} completed in {result.duration_ms}ms")
            if result.data:
                console.print(json.dumps(result.data, indent=2, default=str))
        else:
            console.print(f"[red]✗[/red] {result.agent_name}: {result.task} failed — {result.error}")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


# ---- Stats ----

@cli.command()
def stats():
    """Show collection statistics."""
    console.print(BANNER)

    systems = db.execute("SELECT COUNT(*) as cnt FROM systems")
    roms = db.execute("SELECT SUM(rom_count) as cnt FROM systems")
    emulators = db.execute("SELECT COUNT(*) as cnt FROM emulators")
    healthy = db.execute("SELECT COUNT(*) as cnt FROM emulators WHERE is_healthy=1")
    backups = db.execute("SELECT COUNT(*) as cnt FROM backups")

    table = Table(title="Collection Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Systems", str(systems[0]["cnt"] if systems else 0))
    table.add_row("Total ROMs", f"{(roms[0]['cnt'] or 0):,}" if roms else "0")
    table.add_row("Emulators", str(emulators[0]["cnt"] if emulators else 0))
    table.add_row("Healthy Emulators", str(healthy[0]["cnt"] if healthy else 0))
    table.add_row("Backups", str(backups[0]["cnt"] if backups else 0))

    console.print(table)


# ---- Releases / Emulator Updates ----

@cli.group()
def releases():
    """Check emulator GitHub releases for updates."""
    pass


@releases.command("check")
@click.option("--emulator", "-e", default=None, help="Check a specific emulator")
def releases_check(emulator):
    """Check for emulator updates via GitHub releases."""
    from engines.release_checker import check_all_emulators, check_single_emulator

    if emulator:
        console.print(f"[bold]Checking {emulator} for updates...[/bold]")
        result = check_single_emulator(emulator)
        if not result:
            console.print(f"[red]Failed to check {emulator}[/red]")
            return
        table = Table(title=f"{emulator} Update Check")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Local Version", str(result.get("local_version", "unknown")))
        table.add_row("Latest Release", result.get("latest_tag", "?"))
        table.add_row("Published", result.get("published", "?"))
        table.add_row("Download URL", result.get("download_url", "none")[:80] if result.get("download_url") else "none")
        console.print(table)
    else:
        console.print("[bold]Checking all tracked emulators for updates...[/bold]\n")
        results = check_all_emulators()
        table = Table(title="Emulator Update Status")
        table.add_column("Emulator", style="cyan")
        table.add_column("Installed")
        table.add_column("Local Ver")
        table.add_column("Latest")
        table.add_column("Update?")
        for r in results:
            inst = "[green]Yes[/green]" if r["installed"] else "[dim]No[/dim]"
            upd = "[yellow]YES[/yellow]" if r["update_available"] else "[green]OK[/green]"
            table.add_row(r["emulator"], inst, str(r.get("local_version", "?"))[:25],
                          r.get("latest_tag", "?"), upd)
        console.print(table)
        updates = [r for r in results if r["update_available"]]
        console.print(f"\n[bold]{len(updates)} updates available[/bold] out of {len(results)} tracked")


@releases.command("report")
def releases_report():
    """Generate a full emulator update report."""
    from engines.release_checker import get_update_report
    console.print("[bold]Generating update report...[/bold]\n")
    report = get_update_report()
    output_dir = Path(cfg_get("paths.output_root", ""))
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "emulator_update_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    console.print(f"[green]✓[/green] Report saved: {report_path}")
    console.print(f"  Checked: {report['checked']}, Updates: {report['updates_available']}")


@releases.command("download")
@click.argument("emulator_name")
@click.option("--target-dir", default=None, help="Override download directory")
def releases_download(emulator_name, target_dir):
    """M11 — Download the latest release for an emulator."""
    from engines.update_applier import download_emulator_update
    console.print(f"[bold]Downloading latest release for {emulator_name}...[/bold]")
    result = download_emulator_update(emulator_name, target_dir=target_dir)
    if result.get("error"):
        console.print(f"[red]Error: {result['error']}[/red]")
        return
    console.print(f"[green]✓[/green] Downloaded: {result['filename']}")
    console.print(f"  Path: {result['file']}")
    console.print(f"  Size: {result['size_bytes']:,} bytes")
    console.print(f"  Tag:  {result.get('latest_tag', '?')}")


@releases.command("apply")
@click.argument("emulator_name")
@click.argument("update_source")
@click.option("--method", type=click.Choice(["auto", "copy", "extract", "script"]), default="auto")
@click.option("--test-cmd", default=None, help="Command to verify the update")
@click.option("--dry-run", is_flag=True, help="Snapshot only, do not apply")
def releases_apply(emulator_name, update_source, method, test_cmd, dry_run):
    """M11 — Apply an update: snapshot → apply → test → commit/rollback."""
    from engines.update_applier import apply_update
    console.print(f"[bold]Applying update to {emulator_name}...[/bold]")
    if dry_run:
        console.print("[yellow]DRY RUN — will snapshot but not modify files.[/yellow]")
    result = apply_update(emulator_name, update_source, method=method,
                          test_cmd=test_cmd, dry_run=dry_run)
    if result.get("error"):
        console.print(f"[red]Error: {result['error']}[/red]")
        return
    status = result.get("status", "unknown")
    color = "green" if status == "committed" else ("yellow" if "dry_run" in status else "red")
    console.print(f"[{color}]Status: {status}[/{color}]")
    for step in result.get("steps", []):
        icon = "✓" if step["status"] in ("ok", "passed", "applied", "extracted") else "✗"
        console.print(f"  {icon} {step['step']}: {step['status']}")
    if result.get("new_version"):
        console.print(f"\n  Old version: {result.get('old_version')}")
        console.print(f"  New version: {result['new_version']}")


@releases.command("rollback")
@click.argument("update_id", type=int)
def releases_rollback(update_id):
    """M11 — Rollback a previously applied update by its ID."""
    from engines.update_applier import rollback_update
    console.print(f"[bold]Rolling back update {update_id}...[/bold]")
    result = rollback_update(update_id)
    if result.get("error"):
        console.print(f"[red]Error: {result['error']}[/red]")
        return
    console.print(f"[green]✓[/green] Rolled back: {result.get('program', '')} (id={update_id})")
    console.print(f"  Restored files: {result.get('restored_files', 0)}")


@releases.command("status")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def releases_status(json_out):
    """M11 — Show update pipeline status: pending queue + recent history."""
    from engines.update_applier import get_update_status
    result = get_update_status()
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    console.print(f"[bold]Pending updates:[/bold] {result['pending']}")
    for q in result.get("queue", []):
        console.print(f"  [{q['id']}] {q['program_name']} — {q['status']}")
    console.print(f"\n[bold]Recent history:[/bold] {result['history_count']} entries")
    for h in result.get("history", [])[:10]:
        console.print(f"  [{h['id']}] {h['program_name']}  {h.get('old_version','')} → {h.get('new_version','')}  {h['status']}")


@releases.command("scan-versions")
@click.option("--emu-root", default=None, help="Override emulators root directory")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def releases_scan_versions(emu_root, json_out):
    """M12 — Scan all emulators, detect versions, persist to DB."""
    from engines.version_tracker import scan_emulator_versions
    console.print("[bold]Scanning emulator versions...[/bold]")
    results = scan_emulator_versions(emu_root)
    if json_out:
        console.print_json(json.dumps(results, indent=2, default=str))
        return
    table = Table(title="Emulator Version Scan")
    table.add_column("Emulator", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Healthy", style="yellow")
    table.add_column("Changed", style="magenta")
    for r in results:
        if "error" in r:
            console.print(f"[red]{r['error']}[/red]")
            continue
        changed = "[bold green]YES[/bold green]" if r.get("version_changed") else ""
        healthy = "[green]✓[/green]" if r.get("is_healthy") else "[red]✗[/red]"
        table.add_row(r["name"], r.get("version", "?"), healthy, changed)
    console.print(table)
    console.print(f"\n[bold]{len(results)} emulators scanned[/bold]")


@releases.command("outdated")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def releases_outdated(json_out):
    """M12 — Check tracked emulators for available updates (compares local vs remote)."""
    from engines.version_tracker import get_outdated
    console.print("[bold]Checking for outdated emulators...[/bold]")
    result = get_outdated()
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    if not result.get("outdated"):
        console.print("[green]All tracked emulators are up to date![/green]")
        return
    table = Table(title=f"Outdated Emulators ({result['count']}/{result['total_tracked']})")
    table.add_column("Emulator", style="cyan")
    table.add_column("Local", style="red")
    table.add_column("Remote", style="green")
    table.add_column("Published")
    for o in result["outdated"]:
        table.add_row(o["emulator"], str(o.get("local_version", "?")),
                       o.get("remote_version", "?"), o.get("published", "")[:10])
    console.print(table)


@releases.command("stage")
@click.argument("emulator_name")
@click.option("--target-dir", default=None, help="Override quarantine directory")
def releases_stage(emulator_name, target_dir):
    """M12 — Download an update to quarantine staging (does not apply)."""
    from engines.version_tracker import stage_update
    console.print(f"[bold]Staging update for {emulator_name}...[/bold]")
    result = stage_update(emulator_name, target_dir=target_dir)
    if result.get("error"):
        console.print(f"[red]Error: {result['error']}[/red]")
        return
    console.print(f"[green]✓[/green] Staged: {result['filename']}")
    console.print(f"  Quarantine ID: {result.get('quarantine_id')}")
    console.print(f"  Path: {result['filepath']}")
    console.print(f"  Size: {result['size_bytes']:,} bytes")
    console.print(f"  SHA256: {result.get('sha256', '')[:16]}...")
    console.print(f"  Tag: {result.get('release_tag', '?')}")


@releases.command("quarantine")
@click.option("--emulator", "-e", default=None, help="Filter by emulator name")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def releases_quarantine(emulator, json_out):
    """M12 — List all quarantined (staged) updates."""
    from engines.version_tracker import list_quarantine
    items = list_quarantine(emulator)
    if json_out:
        console.print_json(json.dumps(items, indent=2, default=str))
        return
    if not items:
        console.print("[dim]No quarantined updates.[/dim]")
        return
    table = Table(title="Quarantined Updates")
    table.add_column("ID", style="cyan")
    table.add_column("Emulator")
    table.add_column("Filename")
    table.add_column("Size")
    table.add_column("Status", style="yellow")
    table.add_column("Staged")
    for q in items:
        size = f"{q.get('size_bytes', 0):,}"
        table.add_row(str(q["id"]), q["emulator_name"], q["filename"],
                       size, q["status"], q.get("staged_at", "")[:16])
    console.print(table)


@releases.command("apply-staged")
@click.argument("quarantine_id", type=int)
@click.option("--test-cmd", default=None, help="Command to verify the update")
@click.option("--dry-run", is_flag=True, help="Snapshot only, do not apply")
def releases_apply_staged(quarantine_id, test_cmd, dry_run):
    """M12 — Apply a quarantined update (verify → backup → apply → test)."""
    from engines.version_tracker import apply_staged_update
    console.print(f"[bold]Applying quarantined update #{quarantine_id}...[/bold]")
    if dry_run:
        console.print("[yellow]DRY RUN — will snapshot but not modify files.[/yellow]")
    result = apply_staged_update(quarantine_id, test_cmd=test_cmd, dry_run=dry_run)
    if result.get("error"):
        console.print(f"[red]Error: {result['error']}[/red]")
        return
    status = result.get("status", "unknown")
    color = "green" if status == "committed" else ("yellow" if "dry_run" in status else "red")
    console.print(f"[{color}]Status: {status}[/{color}]")
    for step in result.get("steps", []):
        icon = "✓" if step["status"] in ("ok", "passed", "applied", "extracted") else "✗"
        console.print(f"  {icon} {step['step']}: {step['status']}")


@releases.command("tracker-summary")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def releases_tracker_summary(json_out):
    """M12 — Show version tracking summary: tracked count, quarantined, recent changes."""
    from engines.version_tracker import tracker_summary
    result = tracker_summary()
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    console.print(f"[bold]Tracked emulators:[/bold] {result['tracked_emulators']}")
    console.print(f"[bold]Version records:[/bold]   {result['total_version_records']}")
    console.print(f"[bold]Quarantined:[/bold]        {result['quarantined_updates']}")
    changes = result.get("recent_changes", [])
    if changes:
        console.print("\n[bold]Recent version changes:[/bold]")
        for c in changes[:10]:
            console.print(f"  {c.get('emulator_name', '')} → {c.get('version', '')}  ({c.get('source', '')}  {c.get('detected_at', '')[:16]})")


# ---- M13 Dependency Conflict Detector ----

@cli.group()
def deps():
    """M13 — Dependency conflict detection for emulators."""
    pass


@deps.command("scan")
@click.option("--emu-root", default=None, help="Override emulators root")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def deps_scan(emu_root, json_out):
    """M13 — Scan all emulators for shared DLL dependencies."""
    from engines.dependency_detector import dependency_report
    console.print("[bold]Scanning emulator dependencies...[/bold]")
    result = dependency_report(emu_root)
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    console.print(f"[bold]Emulators scanned:[/bold] {result['emulators_scanned']}")
    console.print(f"[bold]Total shared DLLs:[/bold] {result['total_shared_dlls']}")
    console.print(f"[bold]Unique DLLs:[/bold]       {result['unique_dlls']}")
    c = result["conflicts"]
    console.print(f"\n[bold]Conflicts:[/bold] {c['total']} ({c['critical']} critical, {c['warning']} warnings, {c['info']} info)")
    for det in c["details"]:
        sev_color = {"critical": "red", "warning": "yellow", "info": "cyan"}.get(det["severity"], "white")
        console.print(f"  [{sev_color}][{det['severity'].upper()}][/{sev_color}] {det['dll_name']}: {det['message']}")
        if det.get("resolution"):
            console.print(f"    → {det['resolution']}")
    if result.get("runtime_usage"):
        console.print("\n[bold]Runtime usage:[/bold]")
        for rt, count in list(result["runtime_usage"].items())[:10]:
            console.print(f"  {rt}: {count} emulators")


@deps.command("conflicts")
@click.option("--emu-root", default=None, help="Override emulators root")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def deps_conflicts(emu_root, json_out):
    """M13 — Detect DLL version conflicts across emulators."""
    from engines.dependency_detector import detect_conflicts, scan_all_dependencies
    dep_map = scan_all_dependencies(emu_root)
    conflicts = detect_conflicts(dep_map)
    if json_out:
        console.print_json(json.dumps([c.to_dict() for c in conflicts], indent=2, default=str))
        return
    if not conflicts:
        console.print("[green]No dependency conflicts detected![/green]")
        return
    table = Table(title=f"Dependency Conflicts ({len(conflicts)})")
    table.add_column("Severity", style="bold")
    table.add_column("DLL")
    table.add_column("Emulators")
    table.add_column("Resolution")
    for c in conflicts:
        sev_color = {"critical": "red", "warning": "yellow", "info": "cyan"}.get(c.severity, "white")
        table.add_row(f"[{sev_color}]{c.severity.upper()}[/{sev_color}]",
                       c.dll_name, ", ".join(c.emulators[:5]),
                       c.resolution[:80] + "..." if len(c.resolution) > 80 else c.resolution)
    console.print(table)


@deps.command("check-update")
@click.argument("emulator_name")
@click.option("--update-dir", default=None, help="Path to update files to compare")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def deps_check_update(emulator_name, update_dir, json_out):
    """M13 — Check if updating an emulator would introduce dependency conflicts."""
    from engines.dependency_detector import check_update_conflicts
    result = check_update_conflicts(emulator_name, update_dir=update_dir)
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
        return
    safe = result.get("safe_to_update", True)
    color = "green" if safe else "yellow"
    console.print(f"[bold]Emulator:[/bold] {emulator_name}")
    console.print(f"[bold]Current DLLs:[/bold] {result['current_dll_count']}")
    console.print(f"[{color}]Safe to update: {'YES' if safe else 'REVIEW NEEDED'}[/{color}]")
    changes = result.get("changes", {})
    if changes.get("added"):
        console.print(f"  [green]+ {len(changes['added'])} new DLLs[/green]")
    if changes.get("removed"):
        console.print(f"  [red]- {len(changes['removed'])} removed DLLs[/red]")
    if changes.get("changed"):
        console.print(f"  [yellow]~ {len(changes['changed'])} changed DLLs[/yellow]")
    for issue in result.get("potential_cross_conflicts", []):
        console.print(f"  [yellow]⚠ {issue['dll']} conflicts with {issue['other_emulator']}[/yellow]")


@deps.command("summary")
@click.option("--emu-root", default=None, help="Override emulators root")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def deps_summary(emu_root, json_out):
    """M13 — Quick dependency summary: counts and conflict overview."""
    from engines.dependency_detector import dependency_summary
    result = dependency_summary(emu_root)
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    console.print(f"[bold]Emulators:[/bold] {result['emulators_scanned']}")
    console.print(f"[bold]Shared DLLs:[/bold] {result['total_shared_dlls']} total, {result['unique_dlls']} unique")
    console.print(f"[bold]Conflicts:[/bold] {result['conflicts_critical']} critical, {result['conflicts_warning']} warnings, {result['conflicts_info']} info")


# ---- M14 Pre/Post Update Snapshot Verification ----

@cli.group()
def snapshots():
    """M14 — Pre/post update snapshot verification."""
    pass


@snapshots.command("capture")
@click.argument("target_path")
@click.option("--name", default=None, help="Snapshot name (auto-generated if not set)")
@click.option("--type", "snap_type", type=click.Choice(["pre", "post", "manual"]), default="manual")
@click.option("--no-hash", is_flag=True, help="Skip SHA256 hashing (faster)")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def snapshots_capture(target_path, name, snap_type, no_hash, json_out):
    """M14 — Capture a directory snapshot (file list, sizes, hashes)."""
    from engines.snapshot_verify import capture_snapshot
    console.print(f"[bold]Capturing {snap_type} snapshot of {target_path}...[/bold]")
    try:
        snap = capture_snapshot(target_path, name=name, snapshot_type=snap_type,
                                compute_hashes=not no_hash)
        if json_out:
            console.print_json(json.dumps(snap.to_dict(), indent=2, default=str))
            return
        console.print(f"[green]✓[/green] Snapshot: {snap.name}")
        console.print(f"  Files: {snap.file_count}")
        console.print(f"  Size:  {snap.total_size:,} bytes")
        console.print(f"  DB ID: {snap.db_id}")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


@snapshots.command("compare")
@click.argument("pre_name")
@click.argument("post_name")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def snapshots_compare(pre_name, post_name, json_out):
    """M14 — Compare two snapshots and show differences."""
    from engines.snapshot_verify import compare_snapshots
    try:
        diff = compare_snapshots(pre_name, post_name)
        if json_out:
            console.print_json(json.dumps(diff.to_dict(), indent=2, default=str))
            return
        s = diff.to_dict()["summary"]
        console.print(f"[bold]Pre:[/bold]  {pre_name}")
        console.print(f"[bold]Post:[/bold] {post_name}")
        console.print(f"  [green]+ Added:[/green]     {s['added']}")
        console.print(f"  [red]- Removed:[/red]   {s['removed']}")
        console.print(f"  [yellow]~ Modified:[/yellow]  {s['modified']}")
        console.print(f"  = Unchanged: {s['unchanged']}")
        if diff.added:
            console.print("\n[green]Added files:[/green]")
            for f in diff.added[:20]:
                console.print(f"  + {f['relative_path']}")
        if diff.removed:
            console.print("\n[red]Removed files:[/red]")
            for f in diff.removed[:20]:
                console.print(f"  - {f['relative_path']}")
        if diff.modified:
            console.print("\n[yellow]Modified files:[/yellow]")
            for f in diff.modified[:20]:
                delta = f.get("size_delta", 0)
                sign = "+" if delta >= 0 else ""
                console.print(f"  ~ {f['relative_path']} ({sign}{delta} bytes)")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


@snapshots.command("verify")
@click.argument("target_path")
@click.argument("pre_name")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def snapshots_verify(target_path, pre_name, json_out):
    """M14 — Verify update by capturing post-snapshot and comparing with pre-snapshot."""
    from engines.snapshot_verify import verify_update
    console.print(f"[bold]Verifying update for {target_path}...[/bold]")
    try:
        report = verify_update(target_path, pre_name)
        if json_out:
            console.print_json(json.dumps(report, indent=2, default=str))
            return
        passed = report.get("verification_passed", False)
        color = "green" if passed else "red"
        console.print(f"[{color}]Verification: {'PASSED' if passed else 'FAILED'}[/{color}]")
        d = report.get("diff", {}).get("summary", {})
        console.print(f"  Added: {d.get('added', 0)}, Removed: {d.get('removed', 0)}, Modified: {d.get('modified', 0)}")
        if report.get("unexpected_changes"):
            console.print(f"  [red]Unexpected changes: {len(report['unexpected_changes'])}[/red]")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


@snapshots.command("list")
@click.option("--type", "snap_type", default=None, help="Filter by type: pre, post, manual")
@click.option("--limit", default=20, help="Max results")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def snapshots_list(snap_type, limit, json_out):
    """M14 — List all recorded snapshots."""
    from engines.snapshot_verify import list_snapshots
    items = list_snapshots(snapshot_type=snap_type, limit=limit)
    if json_out:
        console.print_json(json.dumps(items, indent=2, default=str))
        return
    if not items:
        console.print("[dim]No snapshots recorded.[/dim]")
        return
    table = Table(title="Snapshots")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Files")
    table.add_column("Status", style="yellow")
    table.add_column("Created")
    for s in items:
        table.add_row(str(s["id"]), s["name"], s["snapshot_type"],
                       str(s.get("file_count", 0)), s["status"],
                       s.get("created_at", "")[:16])
    console.print(table)


@snapshots.command("summary")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def snapshots_summary(json_out):
    """M14 — Snapshot system summary."""
    from engines.snapshot_verify import snapshot_summary
    result = snapshot_summary()
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    console.print(f"[bold]Total snapshots:[/bold] {result['total_snapshots']}")
    if result.get("by_type"):
        console.print("[bold]By type:[/bold]")
        for t, c in result["by_type"].items():
            console.print(f"  {t}: {c}")
    if result.get("by_status"):
        console.print("[bold]By status:[/bold]")
        for s, c in result["by_status"].items():
            console.print(f"  {s}: {c}")


# ---- M15 Automated Rollback on Failure ----

@cli.group()
def rollback():
    """M15 — Automated rollback on update failure."""
    pass


@rollback.command("check")
@click.argument("emulator_name")
@click.option("--test-cmd", default=None, help="Custom test command to run")
@click.option("--emu-root", default=None, help="Override emulators root")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def rollback_check(emulator_name, test_cmd, emu_root, json_out):
    """M15 — Run health checks for an emulator (post-update verification)."""
    from engines.auto_rollback import run_health_checks
    result = run_health_checks(emulator_name, test_cmd=test_cmd, emu_root=emu_root)
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    color = "green" if result["all_passed"] else "red"
    console.print(f"[bold]Emulator:[/bold] {emulator_name}")
    console.print(f"[{color}]Health: {'ALL PASSED' if result['all_passed'] else 'FAILED'}[/{color}]")
    for c in result["checks"]:
        icon = "[green]✓[/green]" if c["passed"] else "[red]✗[/red]"
        console.print(f"  {icon} {c['check']}: {c['detail']}")


@rollback.command("trigger")
@click.argument("emulator_name")
@click.option("--reason", default="manual", help="Reason for rollback")
@click.option("--backup-path", default=None, help="Override backup path")
@click.option("--emu-root", default=None, help="Override emulators root")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def rollback_trigger(emulator_name, reason, backup_path, emu_root, json_out):
    """M15 — Trigger an automated rollback for an emulator."""
    from engines.auto_rollback import auto_rollback
    console.print(f"[bold yellow]Rolling back {emulator_name}...[/bold yellow]")
    result = auto_rollback(emulator_name, trigger_reason=reason,
                           backup_path=backup_path, emu_root=emu_root)
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    color = "green" if result["status"] in ("completed", "completed_with_warnings") else "red"
    console.print(f"[{color}]Status: {result['status']}[/{color}]")
    for step in result.get("steps", []):
        icon = "[green]✓[/green]" if step.get("status") in ("ok", "completed") else "[red]✗[/red]"
        console.print(f"  {icon} {step.get('step', '')}: {step.get('detail', '')}")


@rollback.command("post-update")
@click.argument("emulator_name")
@click.option("--update-id", type=int, default=None, help="Update history ID")
@click.option("--test-cmd", default=None, help="Custom test command")
@click.option("--emu-root", default=None, help="Override emulators root")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def rollback_post_update(emulator_name, update_id, test_cmd, emu_root, json_out):
    """M15 — Post-update check: verify health and auto-rollback if failed."""
    from engines.auto_rollback import post_update_check
    result = post_update_check(emulator_name, update_id=update_id,
                               test_cmd=test_cmd, emu_root=emu_root)
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    status = result["status"]
    color = "green" if status == "healthy" else "yellow" if status == "rollback_triggered" else "red"
    console.print(f"[{color}]{emulator_name}: {status}[/{color}]")
    if result.get("action") == "auto_rollback":
        rb = result.get("rollback", {})
        console.print(f"  Rollback status: {rb.get('status', 'unknown')}")


@rollback.command("policy")
@click.argument("emulator_name")
@click.option("--enable/--disable", default=True, help="Enable or disable auto-rollback")
@click.option("--test-cmd", default=None, help="Test command to run after updates")
@click.option("--max-age", type=int, default=None, help="Max rollback age in hours")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def rollback_policy(emulator_name, enable, test_cmd, max_age, json_out):
    """M15 — Set rollback policy for an emulator."""
    from engines.auto_rollback import set_policy, get_policy
    if test_cmd is not None or max_age is not None:
        kwargs = {"auto_rollback_enabled": enable}
        if test_cmd is not None:
            kwargs["test_cmd"] = test_cmd
        if max_age is not None:
            kwargs["max_rollback_age_hours"] = max_age
        result = set_policy(emulator_name, **kwargs)
    else:
        result = get_policy(emulator_name)
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    console.print(f"[bold]Policy for {emulator_name}:[/bold]")
    console.print(f"  Auto-rollback: {'enabled' if result.get('auto_rollback_enabled') else 'disabled'}")
    console.print(f"  Health check:  {'required' if result.get('health_check_required') else 'optional'}")
    console.print(f"  Test cmd:      {result.get('test_cmd') or '(none)'}")
    console.print(f"  Max age:       {result.get('max_rollback_age_hours', 72)}h")


@rollback.command("list")
@click.option("--emulator", "-e", default=None, help="Filter by emulator")
@click.option("--limit", default=20, help="Max results")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def rollback_list(emulator, limit, json_out):
    """M15 — List rollback history."""
    from engines.auto_rollback import list_rollbacks
    items = list_rollbacks(emulator_name=emulator, limit=limit)
    if json_out:
        console.print_json(json.dumps(items, indent=2, default=str))
        return
    if not items:
        console.print("[dim]No rollbacks recorded.[/dim]")
        return
    table = Table(title="Rollback History")
    table.add_column("ID", style="cyan")
    table.add_column("Emulator")
    table.add_column("Reason")
    table.add_column("Status")
    table.add_column("Created")
    for r in items:
        table.add_row(str(r["id"]), r["emulator_name"],
                       r["trigger_reason"][:40], r["status"],
                       r.get("created_at", "")[:16])
    console.print(table)


@rollback.command("summary")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def rollback_summary_cmd(json_out):
    """M15 — Rollback system summary."""
    from engines.auto_rollback import rollback_summary
    result = rollback_summary()
    if json_out:
        console.print_json(json.dumps(result, indent=2, default=str))
        return
    console.print(f"[bold]Total rollbacks:[/bold] {result['total_rollbacks']}")
    console.print(f"[bold]Policies:[/bold] {result['policies_configured']} configured, {result['policies_enabled']} enabled")
    if result.get("by_status"):
        console.print("[bold]By status:[/bold]")
        for s, c in result["by_status"].items():
            console.print(f"  {s}: {c}")


# ---- External Tools ----

@cli.group()
def tools():
    """External tool integration (MAME, Igir, Flips, Skyscraper)."""
    pass


@tools.command("discover")
def tools_discover():
    """Discover installed external tools."""
    from engines.external_tools import discover_tools
    found = discover_tools()
    table = Table(title="External Tools")
    table.add_column("Tool", style="cyan")
    table.add_column("Status")
    table.add_column("Path")
    for name, info in found.items():
        status = "[green]Installed[/green]" if info["installed"] else "[red]Missing[/red]"
        table.add_row(name, status, info.get("path") or "")
    console.print(table)


@tools.command("mame-version")
def tools_mame_version():
    """Show MAME version and location."""
    from engines.external_tools import MAMETool
    mame = MAMETool()
    if not mame.available:
        console.print("[red]MAME not found[/red]")
        return
    version = mame.get_version()
    console.print(f"MAME: {version}")
    console.print(f"Path: {mame.exe}")


@tools.command("mame-verify")
@click.option("--rompath", default=None, help="ROM directory to verify")
def tools_mame_verify(rompath):
    """Verify MAME ROMs."""
    from engines.external_tools import MAMETool
    mame = MAMETool()
    if not mame.available:
        console.print("[red]MAME not found[/red]")
        return
    console.print("[bold]Running MAME ROM verification (may take a while)...[/bold]")
    result = mame.verify_roms(rompath)
    if result["success"]:
        console.print(result["stdout"][-2000:] if len(result["stdout"]) > 2000 else result["stdout"])
    else:
        console.print(f"[red]Verification failed: {result['stderr'][:500]}[/red]")


@tools.command("mame-listxml")
@click.option("--output", "-o", default=None, help="Output file path (default: output_root/mame_listxml.xml)")
@click.option("--hyperspin", is_flag=True, help="Also convert to HyperSpin XML format")
@click.option("--roms-dir", default=None, help="Filter to ROMs present in this directory")
def tools_mame_listxml(output, hyperspin, roms_dir):
    """Generate MAME -listxml output for ROM auditing and database generation."""
    from engines.external_tools import MAMETool
    mame = MAMETool()
    if not mame.available:
        console.print("[red]MAME not found[/red]")
        return

    output_dir = Path(cfg_get("paths.output_root", ""))
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output or str(output_dir / "mame_listxml.xml")

    console.print(f"[bold]Running MAME -listxml (may take 2-5 minutes)...[/bold]")
    result = mame.list_xml(out_file)

    if result["success"]:
        size_mb = Path(out_file).stat().st_size / (1024 * 1024) if Path(out_file).exists() else 0
        console.print(f"[green]✓[/green] listxml saved: {out_file} ({size_mb:.1f} MB)")

        if hyperspin:
            console.print("[bold]Converting to HyperSpin XML format...[/bold]")
            try:
                from engines.external_tools import convert_mame_xml_to_hyperspin
                hs_out = str(output_dir / "MAME_HyperSpin.xml")
                roms_filter = Path(roms_dir) if roms_dir else None
                stats = convert_mame_xml_to_hyperspin(out_file, hs_out, roms_dir=roms_filter)
                console.print(f"[green]✓[/green] HyperSpin XML: {hs_out}")
                console.print(f"  MAME total: {stats.get('mame_total', 0):,} | With ROMs: {stats.get('with_roms', 0):,} | Written: {stats.get('written', 0):,}")
            except (ImportError, AttributeError):
                console.print("[yellow]HyperSpin conversion not available — use OpenHands bridge for this step[/yellow]")
                console.print(f"[dim]  openhands_run_task: convert {out_file} to HyperSpin XML at {output_dir}/MAME_HyperSpin.xml[/dim]")
    else:
        console.print(f"[red]listxml failed: {result['stderr'][:500]}[/red]")


# ---- Space Optimizer ----

@cli.group()
def optimize():
    """Disk space optimization tools."""
    pass


@optimize.command("report")
def optimize_report():
    """Generate a full space optimization report."""
    from engines.space_optimizer import full_optimization_report
    console.print("[bold]Analyzing disk usage and finding optimization opportunities...[/bold]\n")
    report = full_optimization_report()

    # Disk summary
    disk = report.get("disk", {})
    console.print(Panel(
        f"Used: {disk.get('drive_used_human', '?')} / "
        f"Free: {disk.get('drive_free_human', '?')} / "
        f"Total: {disk.get('drive_total_human', '?')} "
        f"({disk.get('drive_used_pct', 0)}% used)",
        title="Disk Usage", border_style="blue"))

    # Redundant emulators
    emu = report.get("redundant_emulators", {})
    if emu.get("groups"):
        table = Table(title=f"Redundant Emulator Versions ({emu['redundant_groups']} groups)")
        table.add_column("Base Name", style="cyan")
        table.add_column("Copies", justify="right")
        table.add_column("Total Size")
        table.add_column("Savings")
        table.add_column("Keep")
        for g in emu["groups"][:15]:
            table.add_row(g["base_name"], str(g["count"]),
                          g["total_size_human"], g["potential_savings_human"],
                          g["recommended_keep"])
        console.print(table)
        console.print(f"[bold]Potential savings from emulator consolidation: {emu['potential_savings_human']}[/bold]\n")

    # Recommendations
    recs = report.get("recommendations", [])
    if recs:
        console.print("[bold]Recommendations:[/bold]")
        for i, r in enumerate(recs, 1):
            risk_color = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red"}.get(r["risk"].split()[0], "white")
            console.print(f"  {i}. [bold]{r['action']}[/bold]")
            console.print(f"     {r['details']}")
            console.print(f"     Savings: {r['savings']}  Risk: [{risk_color}]{r['risk']}[/{risk_color}]")

    # Save
    output_dir = Path(cfg_get("paths.output_root", ""))
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "space_optimization_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    console.print(f"\n[dim]Full report saved to: {report_path}[/dim]")


@optimize.command("duplicates")
@click.option("--dir", "-d", "scan_dir", default=None, help="Directory to scan")
@click.option("--min-size", default=1024, help="Minimum file size in bytes")
def optimize_duplicates(scan_dir, min_size):
    """Find duplicate ROM files."""
    from engines.space_optimizer import find_duplicate_roms
    dirs = [scan_dir] if scan_dir else None
    console.print("[bold]Scanning for duplicate files...[/bold]\n")
    result = find_duplicate_roms(rom_dirs=dirs, min_size=min_size)
    console.print(f"Scanned: {result['file_count']:,} files")
    console.print(f"Duplicate groups: {result['duplicate_groups']}")
    console.print(f"[bold]Recoverable space: {result['total_wasted_human']}[/bold]\n")
    for dup in result["duplicates"][:20]:
        console.print(f"  [{dup['count']} copies] {dup['size_human']} — {dup['wasted_human']} wasted")
        for f in dup["files"][:3]:
            console.print(f"    {f}")
        if len(dup["files"]) > 3:
            console.print(f"    ... and {len(dup['files'])-3} more")


@optimize.command("emulators")
def optimize_emulators():
    """Find redundant emulator versions."""
    from engines.space_optimizer import find_redundant_emulators
    console.print("[bold]Analyzing emulator directories...[/bold]\n")
    result = find_redundant_emulators()
    console.print(f"Total emulator dirs: {result['total_dirs']}")
    console.print(f"Redundant groups: {result['redundant_groups']}")
    console.print(f"[bold]Potential savings: {result['potential_savings_human']}[/bold]\n")
    for g in result["groups"]:
        console.print(f"  [bold]{g['base_name']}[/bold] ({g['count']} versions, {g['total_size_human']})")
        console.print(f"    Recommended keep: [green]{g['recommended_keep']}[/green]")
        for v in g["versions"]:
            marker = " ←keep" if v["name"] == g["recommended_keep"] else ""
            console.print(f"      {v['name']} ({v['size_human']}){marker}")


@optimize.command("large-files")
@click.option("--min-mb", default=500, help="Minimum file size in MB")
def optimize_large_files(min_mb):
    """Find the largest files in the collection."""
    from engines.space_optimizer import find_large_files
    console.print(f"[bold]Finding files larger than {min_mb} MB...[/bold]\n")
    files = find_large_files(min_size_mb=min_mb)
    table = Table(title=f"Largest Files (>{min_mb} MB)")
    table.add_column("Size", justify="right")
    table.add_column("Extension")
    table.add_column("Path")
    for f in files:
        table.add_row(f["size_human"], f["extension"], f["path"][-80:])
    console.print(table)


# ---- Drives ----

@cli.group()
def drives():
    """Multi-drive management — scan, assign, and switch arcade drives."""
    pass


@drives.command("scan")
@click.option("--min-gb", default=100, type=float, help="Minimum drive size in GB to include (default: 100)")
def drives_scan(min_gb):
    """Scan all connected drives, fingerprint them, and show arcade content."""
    from engines.drive_index import scan_drives, load_index
    idx = load_index()
    results = scan_drives(min_gb=min_gb)

    primary   = (idx.get("primary") or "").upper()
    secondary = (idx.get("secondary") or "").upper()
    tertiary  = (idx.get("tertiary") or "").upper()

    table = Table(title="Connected Drives (Fingerprint Index)", show_lines=True)
    table.add_column("Letter", style="bold cyan", width=6)
    table.add_column("Fingerprint", style="dim", width=14)
    table.add_column("Label", width=18)
    table.add_column("Size", justify="right", width=8)
    table.add_column("Free", justify="right", width=8)
    table.add_column("Arcade?", width=8)
    table.add_column("Root", width=10)
    table.add_column("Role", style="bold yellow", width=10)

    for d in results:
        letter = d["letter"].upper()
        role = ""
        if letter == primary:
            role = "PRIMARY"
        elif letter == secondary:
            role = "secondary"
        elif letter == tertiary:
            role = "tertiary"

        arcade_str = "[green]YES[/green]" if d["is_arcade"] else "[dim]no[/dim]"
        if d["is_system"]:
            arcade_str = "[dim]system[/dim]"

        table.add_row(
            f"{letter}:",
            d.get("fingerprint", "")[:12],
            d["label"] or "",
            d["total_human"],
            d["free_human"],
            arcade_str,
            d["arcade_root"] if d["is_arcade"] else "",
            role,
        )

    console.print(table)
    console.print(f"\n[dim]Indexed drives: {len(idx.get('drives', {}))} total  |  "
                  f"Use 'drives reconcile' to auto-heal or 'drives index' to see full history.[/dim]")


@drives.command("status")
def drives_status():
    """Show current drive role assignments with fingerprints and live disk usage."""
    from engines.drive_index import drive_status
    status = drive_status()

    table = Table(title="Drive Assignments (Smart Index v2)", show_lines=True)
    table.add_column("Role", style="bold cyan", width=10)
    table.add_column("Letter", width=7)
    table.add_column("Fingerprint", style="dim", width=14)
    table.add_column("Path", width=24)
    table.add_column("Label", width=16)
    table.add_column("Type", width=6)
    table.add_column("Size", justify="right", width=8)
    table.add_column("Free", justify="right", width=8)
    table.add_column("OK?", width=5)

    for role in ("primary", "secondary", "tertiary"):
        info = status["drives"].get(role, {})
        if not info.get("assigned"):
            table.add_row(role, "[dim]—[/dim]", "", "[dim]not assigned[/dim]", "", "", "", "", "")
            continue
        connected = info.get("connected", False)
        root_ok   = info.get("root_exists", False)
        ok_str    = "[green]✓[/green]" if (connected and root_ok) else (
                    "[yellow]?[/yellow]" if connected else "[red]✗[/red]")
        table.add_row(
            role,
            f"{info['letter']}:",
            info.get("fingerprint", "")[:12],
            info.get("path", ""),
            info.get("label", ""),
            info.get("drive_type", "?"),
            info.get("total_human", ""),
            info.get("free_human", ""),
            ok_str,
        )

    console.print(table)
    console.print(f"[dim]Indexed: {status.get('total_indexed', 0)} drives  |  "
                  f"Last scan: {status.get('last_scan', 'never')}[/dim]")


@drives.command("set")
@click.argument("role", type=click.Choice(["primary", "secondary", "tertiary"]))
@click.argument("letter")
@click.option("--root", default=None, help="Arcade subfolder on the drive (default: Arcade)")
def drives_set(role, letter, root):
    """Assign a drive letter to a role. Drive is tracked by fingerprint internally.

    Example: drives set primary E
    """
    from engines.drive_index import assign_role, _detect_arcade_content
    import os

    letter = letter.upper().strip(":\\")
    drive_path = f"{letter}:\\"

    if not os.path.exists(drive_path):
        console.print(f"[red]Drive {letter}: is not connected.[/red]")
        return

    if root is None:
        arcade_info = _detect_arcade_content(letter)
        root = arcade_info["arcade_root"] if arcade_info["found"] else "Arcade"

    try:
        idx = assign_role(role, letter, root)
        fp = idx["roles"].get(role, "")
        from core.config import reload_config
        reload_config()

        console.print(f"[green]✓[/green] {role} → {letter}:\\{root}  (fingerprint: {fp[:12]})")
        console.print(f"[dim]Drive tracked by identity — if letter changes, toolkit auto-heals.[/dim]")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


@drives.command("auto")
@click.option("--dry-run", is_flag=True, help="Show what would be assigned without saving")
def drives_auto(dry_run):
    """Auto-detect drive roles using smart fingerprint-based indexing."""
    from engines.drive_index import reconcile, load_index
    from core.config import reload_config

    console.print("[bold]Scanning & fingerprinting all drives...[/bold]")

    if dry_run:
        idx = reconcile(detect_type=False)
        console.print("[yellow](dry-run — showing results but not applying)[/yellow]")
    else:
        idx = reconcile(detect_type=False)

    primary   = idx.get("primary")
    secondary = idx.get("secondary")
    tertiary  = idx.get("tertiary")
    arc_root  = idx.get("arcade_root", "Arcade")
    sec_root  = idx.get("secondary_root", "Arcade")

    console.print(f"  primary   → {primary}:\\{arc_root}" if primary else "  primary   → [red]not detected[/red]")
    console.print(f"  secondary → {secondary}:\\{sec_root}" if secondary and secondary != primary else "  secondary → [dim]none[/dim]")
    console.print(f"  tertiary  → {tertiary}:" if tertiary and tertiary != secondary else "  tertiary  → [dim]none[/dim]")

    events = idx.get("events", [])
    if events:
        console.print(f"\n[bold]Events detected ({len(events)}):[/bold]")
        for ev in events:
            etype = ev.get("type", "")
            if etype == "letter_changed":
                console.print(f"  [yellow]⚡ Drive letter changed:[/yellow] {ev['old_letter']}: → {ev['new_letter']}: ({ev.get('label', '')})")
            elif etype == "new_arcade_drive":
                console.print(f"  [green]+ New arcade drive:[/green] {ev['letter']}: ({ev.get('label', '')})")
            elif etype == "drive_disconnected":
                console.print(f"  [red]- Drive disconnected:[/red] {ev.get('last_letter', '?')}: ({ev.get('label', '')})")
            elif etype == "role_drive_offline":
                console.print(f"  [red]⚠ {ev['role']} drive offline:[/red] {ev.get('last_letter', '?')}:")

    indexed = len(idx.get("drives", {}))
    console.print(f"\n[green]✓[/green] {indexed} drives indexed  |  Assignments saved to drives.json")
    if not dry_run:
        reload_config()
        console.print("[green]✓[/green] Config reloaded with current drive letters")


@drives.command("clear")
@click.argument("role", type=click.Choice(["primary", "secondary", "tertiary", "all"]))
def drives_clear(role):
    """Clear a drive assignment so auto-detect runs again."""
    from engines.drive_index import load_index, save_index
    from core.config import reload_config

    idx = load_index()
    roles_to_clear = ["primary", "secondary", "tertiary"] if role == "all" else [role]
    root_key_map = {"primary": "arcade_root", "secondary": "secondary_root", "tertiary": "tertiary_root"}
    for r in roles_to_clear:
        old_fp = idx["roles"].get(r)
        if old_fp and old_fp in idx["drives"]:
            idx["drives"][old_fp]["role"] = None
        idx["roles"][r] = None
        idx[r] = None
        idx[root_key_map[r]] = None
    save_index(idx)
    reload_config()
    console.print(f"[green]✓[/green] Cleared {role} assignment. Run 'drives auto' to re-detect.")


@drives.command("reconcile")
@click.option("--detect-type", is_flag=True, help="Also detect NVMe/SSD/HDD (slower, uses PowerShell)")
def drives_reconcile(detect_type):
    """Full reconciliation: re-scan, detect letter changes, discover new drives, heal roles.

    This is the smart core of the drive index system.  It:
      - Fingerprints every connected drive (volume serial + content hash)
      - Matches each to a known drive in the index
      - Detects when a drive changed its letter (same serial, different letter)
      - Discovers brand-new drives and adds them to the index
      - Marks disconnected drives as offline (but remembers them)
      - Auto-assigns roles to unassigned arcade drives
    """
    from engines.drive_index import reconcile
    from core.config import reload_config

    console.print("[bold]Running full drive reconciliation...[/bold]")
    idx = reconcile(detect_type=detect_type)
    events = idx.get("events", [])

    if events:
        console.print(f"\n[bold]Events ({len(events)}):[/bold]")
        for ev in events:
            etype = ev.get("type", "")
            if etype == "letter_changed":
                console.print(f"  [yellow]⚡ Letter changed:[/yellow] {ev['old_letter']}: → {ev['new_letter']}: "
                              f"[dim]({ev.get('label', '')})[/dim]")
            elif etype == "new_arcade_drive":
                console.print(f"  [green]+ New arcade drive:[/green] {ev['letter']}: "
                              f"[dim]({ev.get('label', '')})[/dim]")
            elif etype == "drive_disconnected":
                console.print(f"  [red]- Disconnected:[/red] was {ev.get('last_letter', '?')}: "
                              f"[dim]({ev.get('label', '')})[/dim]")
            elif etype == "role_drive_offline":
                console.print(f"  [red]⚠ {ev['role']} drive offline:[/red] was {ev.get('last_letter', '?')}:")
    else:
        console.print("[green]✓[/green] No changes detected — all drives stable.")

    indexed = len(idx.get("drives", {}))
    connected = sum(1 for d in idx.get("drives", {}).values() if d.get("connected"))
    console.print(f"\n[dim]Index: {indexed} total, {connected} connected  |  "
                  f"Roles: P={idx.get('primary', '—')} S={idx.get('secondary', '—')} T={idx.get('tertiary', '—')}[/dim]")
    reload_config()


@drives.command("index")
def drives_index():
    """Show the full drive index — all drives ever seen, including disconnected ones."""
    from engines.drive_index import list_indexed_drives

    drives_list = list_indexed_drives()
    if not drives_list:
        console.print("[dim]No drives indexed yet. Run 'drives reconcile' first.[/dim]")
        return

    table = Table(title="Drive Index (All Known Drives)", show_lines=True)
    table.add_column("Fingerprint", style="dim", width=14)
    table.add_column("Letter", style="bold cyan", width=6)
    table.add_column("Label", width=16)
    table.add_column("Role", style="bold yellow", width=10)
    table.add_column("Type", width=6)
    table.add_column("Status", width=10)
    table.add_column("Arcade", width=8)
    table.add_column("Size", justify="right", width=8)
    table.add_column("First Seen", width=12)
    table.add_column("Last Seen", width=12)

    for d in drives_list:
        status = "[green]online[/green]" if d["connected"] else "[red]offline[/red]"
        role = d.get("role") or "[dim]—[/dim]"
        arcade = "[green]YES[/green]" if d.get("confidence", 0) > 0 else "[dim]no[/dim]"
        first = d.get("first_seen", "")[:10]
        last  = d.get("last_seen", "")[:10]
        size  = f"{d.get('total_gb', 0):.0f} GB" if d.get("total_gb") else ""

        table.add_row(
            d["fingerprint"][:12],
            f"{d['letter']}:",
            d.get("label", ""),
            role,
            d.get("drive_type", "?"),
            status,
            arcade,
            size,
            first,
            last,
        )

    console.print(table)
    online  = sum(1 for d in drives_list if d["connected"])
    offline = sum(1 for d in drives_list if not d["connected"])
    console.print(f"[dim]{len(drives_list)} drives indexed  |  {online} online  |  {offline} offline[/dim]")


@drives.command("detect-type")
@click.option("--all-drives", is_flag=True, help="Detect type for all indexed drives")
@click.argument("letter", default="")
def drives_detect_type(all_drives, letter):
    """Detect drive type (NVMe / SSD / HDD) using PowerShell.

    \b
    Examples:
      drives detect-type D
      drives detect-type --all-drives
    """
    from engines.drive_index import load_index, save_index, _detect_drive_type

    idx = load_index()
    targets = []

    if all_drives:
        targets = [(fp, drv) for fp, drv in idx.get("drives", {}).items() if drv.get("connected")]
    elif letter:
        letter = letter.upper().strip(":\\")
        for fp, drv in idx.get("drives", {}).items():
            if drv.get("current_letter", "").upper() == letter:
                targets = [(fp, drv)]
                break
    else:
        console.print("[red]Provide a drive letter or use --all-drives[/red]")
        return

    if not targets:
        console.print("[dim]No matching connected drives found.[/dim]")
        return

    for fp, drv in targets:
        ltr = drv.get("current_letter", "?")
        console.print(f"  Detecting type for {ltr}:...", end=" ")
        dtype = _detect_drive_type(ltr)
        drv["drive_type"] = dtype
        color = {"NVMe": "green", "SSD": "cyan", "HDD": "yellow"}.get(dtype, "white")
        console.print(f"[{color}]{dtype}[/{color}]")

    save_index(idx)
    console.print(f"[green]✓[/green] Drive types saved to index.")


@drives.command("plan")
@click.argument("source")
@click.argument("dest_drive")
@click.option("--category", "-c", multiple=True,
              type=click.Choice(["all", "roms", "emulators", "media",
                                 "hyperspin", "rocketlauncher", "databases", "settings"]),
              default=["all"], show_default=True,
              help="What to transfer (repeat for multiple)")
def drives_plan(source, dest_drive, category):
    """Calculate space needed to transfer SOURCE to DEST_DRIVE.

    \b
    Examples:
      drives plan D:\\Arcade E
      drives plan D:\\Arcade F --category roms --category emulators
    """
    from engines.drive_transfer import plan_space

    console.print(f"[bold]Calculating space for transfer {source} → {dest_drive}:...[/bold]")
    result = plan_space(source, dest_drive, list(category))

    fits_str = "[green]YES — fits[/green]" if result["fits"] else "[red]NO — not enough space[/red]"

    console.print(Panel(
        f"Needed:    [bold]{result['needed_human']}[/bold]\n"
        f"Available: [bold]{result['available_human']}[/bold]  on {result['dest_drive']}:\\\n"
        f"Margin:    {result['margin_human']}\n"
        f"Fits:      {fits_str}",
        title=f"Space Plan: {source} → {result['dest_drive']}:\\",
        border_style="blue" if result["fits"] else "red",
    ))

    if len(category) > 0 and "all" not in category:
        table = Table(title="Category Breakdown")
        table.add_column("Category")
        table.add_column("Size", justify="right")
        table.add_column("Files", justify="right")
        for cat, info in result["categories"].items():
            table.add_row(cat, info["human"], f"{info['files']:,}")
        console.print(table)

    if not result["fits"]:
        shortage = result["needed_bytes"] - result["available_bytes"]
        from engines.drive_transfer import _human
        console.print(f"\n[red]Short by {_human(shortage)}.[/red]")
        console.print("[dim]Try: drives plan ... --category roms  (skip media to reduce size)[/dim]")


@drives.command("migrate")
@click.argument("source")
@click.argument("dest")
@click.option("--category", "-c", multiple=True,
              type=click.Choice(["all", "roms", "emulators", "media",
                                 "hyperspin", "rocketlauncher", "databases", "settings"]),
              default=["all"], show_default=True,
              help="What to transfer (repeat for multiple)")
@click.option("--verify", is_flag=True, help="Hash-verify every file after copy")
@click.option("--dry-run", is_flag=True, help="Show what would be copied without doing it")
@click.option("--rewrite-paths", is_flag=True, default=True,
              help="After copy, update RocketLauncher INI drive letters (default: on)")
@click.option("--no-rewrite-paths", "rewrite_paths", flag_value=False,
              help="Skip INI path rewriting")
def drives_migrate(source, dest, category, verify, dry_run, rewrite_paths):
    """Copy entire arcade collection from SOURCE to DEST directory.

    \b
    Supports resume — already-copied files are skipped automatically.
    Examples:
      drives migrate D:\\Arcade E:\\Arcade
      drives migrate D:\\Arcade F:\\Arcade --category roms --category emulators
      drives migrate D:\\Arcade E:\\Arcade --verify --dry-run
    """
    from engines.drive_transfer import (
        plan_space, build_plan, execute_transfer,
        transfer_summary, rewrite_ini_paths, _human,
    )
    from pathlib import Path as _Path
    import os

    src = source.rstrip("\\")
    dst = dest.rstrip("\\")
    cats = list(category)

    # Pre-check space
    dest_letter = _Path(dst).drive.rstrip(":\\") if _Path(dst).drive else dst[0]
    space = plan_space(src, dest_letter, cats)
    console.print(f"[bold]Transfer plan:[/bold] {src} → {dst}")
    console.print(f"  Data to copy: [bold]{space['needed_human']}[/bold]")
    console.print(f"  Dest free:    [bold]{space['available_human']}[/bold]")

    if not space["fits"] and not dry_run:
        from engines.drive_transfer import _human as h
        short = space["needed_bytes"] - space["available_bytes"]
        console.print(f"\n[red]✗ Not enough space on {dest_letter}: — short by {_human(short)}[/red]")
        console.print("[dim]Use --category to select a subset, or free space on the destination.[/dim]")
        return

    if dry_run:
        console.print("\n[yellow](dry-run — no files will be copied)[/yellow]")

    if not dry_run and not click.confirm(f"\nProceed with transfer?"):
        console.print("[dim]Cancelled.[/dim]")
        return

    # Build plan (loads manifest for resume)
    console.print("\n[bold]Building file list...[/bold]")
    plan = build_plan(src, dst, cats, verify=verify)

    pending = sum(1 for f in plan.files if f.status == "pending")
    skipped = sum(1 for f in plan.files if f.status in ("copied", "verified", "skipped"))
    console.print(f"  Total files:   {plan.total_files:,}  ({_human(plan.total_bytes)})")
    console.print(f"  To copy:       {pending:,}")
    console.print(f"  Already done:  {skipped:,}  (will skip)")

    if pending == 0 and not dry_run:
        console.print("\n[green]✓ All files already transferred.[/green]")
    else:
        # Execute with progress
        last_pct = [-1]

        def _progress(state: dict) -> None:
            pct = int(state["pct"])
            if pct != last_pct[0] and pct % 5 == 0:
                last_pct[0] = pct
                console.print(
                    f"  [{pct:3d}%] {state['bytes_done_human']} / {state['bytes_total_human']}"
                    f"  {state['speed_human']}  ETA {state['eta_sec']//60}m{state['eta_sec']%60}s"
                    f"  {state['files_done']:,}/{state['files_total']:,} files"
                )

        result = execute_transfer(plan, verify=verify, dry_run=dry_run, progress_cb=_progress)
        summary = transfer_summary(result, plan)

        console.print(Panel(
            f"Copied:   {summary['copied']:,} files  ({summary['bytes_human']})\n"
            f"Skipped:  {summary['skipped']:,} files  (already done)\n"
            f"Failed:   {summary['failed']:,}\n"
            f"Verified: {summary['verified_ok']:,} OK  {summary['verified_fail']:,} FAIL\n"
            f"Speed:    {summary['avg_speed']}\n"
            f"Time:     {summary['elapsed_human']}",
            title="Transfer Complete" if not dry_run else "Dry-Run Summary",
            border_style="green" if result.failed == 0 else "yellow",
        ))

        if result.errors:
            console.print(f"\n[red]Errors ({len(result.errors)}):[/red]")
            for e in result.errors[:10]:
                console.print(f"  [red]✗[/red] {e}")

    # Rewrite INI paths (only if actual copy happened)
    if rewrite_paths and not dry_run and result.copied > 0:
        src_letter = _Path(src).drive.rstrip(":\\")
        dst_letter = _Path(dst).drive.rstrip(":\\")
        if src_letter.upper() != dst_letter.upper():
            rl_root = _Path(dst) / "RocketLauncher"
            if rl_root.exists():
                console.print(f"\n[bold]Rewriting INI paths {src_letter}: → {dst_letter}:...[/bold]")
                ini_result = rewrite_ini_paths(str(rl_root), src_letter, dst_letter)
                console.print(
                    f"[green]✓[/green] {ini_result['files_changed']:,} INI files updated"
                    f"  ({ini_result['lines_changed']:,} path references)"
                )
            else:
                console.print(f"\n[dim]No RocketLauncher folder found at {rl_root} — INI rewrite skipped.[/dim]")

    if not dry_run:
        console.print(f"\n[dim]Transfer manifest: {dst}\\.hstk_transfer_manifest.json[/dim]")
        console.print("[dim]Tip: Run 'drives set primary' to switch toolkit to the new drive.[/dim]")


@drives.command("health")
@click.argument("letter", default="")
@click.option("--all-drives", is_flag=True, help="Check all connected non-system drives")
def drives_health(letter, all_drives):
    """Check HDD/SSD health (SMART status, temperature, reallocated sectors).

    \b
    Examples:
      drives health D
      drives health --all-drives
    """
    from engines.drive_transfer import drive_health_check
    from engines.drive_index import scan_drives
    import os

    letters_to_check = []
    if all_drives:
        drives_list = scan_drives(min_gb=0)
        letters_to_check = [d["letter"] for d in drives_list if not d["is_system"]]
    elif letter:
        letters_to_check = [letter.upper().strip(":\\")]
    else:
        console.print("[red]Provide a drive letter (e.g. drives health D) or use --all-drives[/red]")
        return

    for ltr in letters_to_check:
        health = drive_health_check(ltr)
        if not health["connected"]:
            console.print(f"[red]{ltr}: not connected[/red]")
            continue

        smart = health.get("smart", {})
        wmic  = health.get("wmic", {})
        health_str = smart.get("health", "UNKNOWN")
        color = "green" if health_str == "PASSED" else ("red" if health_str == "FAILED" else "yellow")

        lines = [
            f"Drive:       {ltr}:  {health.get('total_gb', '?')} GB total  "
            f"{health.get('free_gb', '?')} GB free  ({health.get('used_pct', '?')}% used)",
        ]
        if wmic:
            lines.append(f"Device:      {wmic.get('caption', '?')}")
            lines.append(f"Interface:   {wmic.get('interface', '?')}  Status: {wmic.get('status', '?')}")
        if smart.get("health"):
            lines.append(f"SMART:       [{color}]{health_str}[/{color}]")
        if smart.get("temperature_c"):
            lines.append(f"Temperature: {smart['temperature_c']}°C")
        if smart.get("reallocated_sectors"):
            rsc = int(smart["reallocated_sectors"])
            rsc_color = "green" if rsc == 0 else ("yellow" if rsc < 5 else "red")
            lines.append(f"Reallocated: [{rsc_color}]{rsc}[/{rsc_color}]  (0 = good)")
        if smart.get("power_on_hours"):
            hours = int(smart["power_on_hours"])
            years = round(hours / 8760, 1)
            lines.append(f"Power-on:    {hours:,} hours  (~{years} years)")
        if smart.get("note"):
            lines.append(f"[dim]{smart['note']}[/dim]")

        console.print(Panel("\n".join(lines), title=f"Drive {ltr}: Health",
                            border_style=color))


@drives.command("compare")
@click.argument("source")
@click.argument("dest")
@click.option("--no-size-check", is_flag=True, help="Skip size comparison (faster)")
@click.option("--show-extra", is_flag=True, help="Also list files only on dest")
def drives_compare(source, dest, no_size_check, show_extra):
    """Compare two directories and show what's missing or out of sync.

    \b
    Use after migration to verify completeness, or to see what needs syncing.
    Examples:
      drives compare "D:\\Arcade" "E:\\Arcade"
      drives compare "D:\\Arcade" "E:\\Arcade" --show-extra
    """
    from engines.drive_transfer import compare_drives

    console.print(f"[bold]Comparing {source} ↔ {dest}...[/bold]")
    console.print("[dim](scanning file trees — may take a minute for large collections)[/dim]")

    result = compare_drives(source, dest, check_size=not no_size_check)

    status = "[green]IN SYNC[/green]" if result["in_sync"] else "[yellow]DIFFERENCES FOUND[/yellow]"
    console.print(Panel(
        f"Source files:  {result['source_total_files']:,}\n"
        f"Dest files:    {result['dest_total_files']:,}\n"
        f"Status:        {status}\n\n"
        f"Missing on dest:    {result['only_in_source_count']:,} files  "
        f"({result['only_in_source_human']})\n"
        f"Extra on dest:      {result['only_in_dest_count']:,} files\n"
        f"Size mismatches:    {result['size_mismatch_count']:,} files  "
        f"({result['size_mismatch_human']})",
        title=f"Compare: {source} ↔ {dest}",
        border_style="green" if result["in_sync"] else "yellow",
    ))

    if result["only_in_source_count"] > 0:
        console.print(f"\n[yellow]Missing on dest ({result['only_in_source_count']:,} files):[/yellow]")
        for p in result["only_in_source"][:30]:
            console.print(f"  [dim]  {p}[/dim]")
        if result["only_in_source_count"] > 30:
            console.print(f"  [dim]  ...and {result['only_in_source_count'] - 30:,} more[/dim]")
        console.print(f"\n[dim]Tip: Run 'drives sync {source} {dest}' to copy missing files.[/dim]")

    if show_extra and result["only_in_dest_count"] > 0:
        console.print(f"\n[dim]Extra on dest ({result['only_in_dest_count']:,} files):[/dim]")
        for p in result["only_in_dest"][:20]:
            console.print(f"  [dim]  {p}[/dim]")

    if result["size_mismatch_count"] > 0:
        console.print(f"\n[yellow]Size mismatches ({result['size_mismatch_count']:,}):[/yellow]")
        for m in result["size_mismatches"][:15]:
            from engines.drive_transfer import _human
            console.print(
                f"  [yellow]{m['path']}[/yellow]  "
                f"src={_human(m['src_size'])}  dst={_human(m['dst_size'])}"
            )


@drives.command("sync")
@click.argument("source")
@click.argument("dest")
@click.option("--delete-extra", is_flag=True,
              help="Mirror mode: also delete files on dest that don't exist in source")
@click.option("--verify", is_flag=True, help="Hash-verify copied files")
@click.option("--dry-run", is_flag=True, help="Show what would be synced without copying")
def drives_sync(source, dest, delete_extra, verify, dry_run):
    """Incrementally sync SOURCE to DEST — copy only new/changed files.

    \b
    Use to keep a secondary drive current with the primary after adding games.
    Only files that are missing or have a different size on dest are copied.
    Examples:
      drives sync "D:\\Arcade" "E:\\Arcade"
      drives sync "D:\\Arcade" "E:\\Arcade" --dry-run
      drives sync "D:\\Arcade" "E:\\Arcade" --delete-extra   # mirror mode
    """
    from engines.drive_transfer import sync_drives, _human

    console.print(f"[bold]Syncing {source} → {dest}[/bold]")
    if dry_run:
        console.print("[yellow](dry-run — no files will be copied)[/yellow]")
    if delete_extra:
        console.print("[yellow](mirror mode — extra files on dest will be deleted)[/yellow]")

    last_pct = [-1]

    def _progress(state: dict) -> None:
        pct = int(state["pct"])
        if pct != last_pct[0] and pct % 10 == 0:
            last_pct[0] = pct
            console.print(
                f"  [{pct:3d}%] {state['bytes_done_human']} / {state['bytes_total_human']}"
                f"  {state['speed_human']}  ETA {state['eta_sec']//60}m{state['eta_sec']%60}s"
                f"  {state['files_done']:,}/{state['files_total']:,} files"
            )

    result = sync_drives(
        source, dest,
        delete_extra=delete_extra,
        verify=verify,
        dry_run=dry_run,
        progress_cb=_progress,
    )

    elapsed = result.elapsed_sec
    speed_bps = result.bytes_copied / elapsed if elapsed > 0 else 0
    elapsed_str = f"{int(elapsed//3600)}h {int((elapsed%3600)//60)}m {int(elapsed%60)}s"

    console.print(Panel(
        f"Copied:   {result.copied:,} files  ({_human(result.bytes_copied)})\n"
        f"Skipped:  {result.skipped:,} files  (already current)\n"
        f"Failed:   {result.failed:,}\n"
        f"Verified: {result.verified_ok:,} OK  {result.verified_fail:,} FAIL\n"
        f"Speed:    {_human(int(speed_bps))}/s\n"
        f"Time:     {elapsed_str}",
        title="Sync Complete" if not dry_run else "Dry-Run Preview",
        border_style="green" if result.failed == 0 else "yellow",
    ))

    if result.errors:
        console.print(f"\n[red]Errors ({len(result.errors)}):[/red]")
        for e in result.errors[:10]:
            console.print(f"  [red]✗[/red] {e}")


@drives.command("rewrite-paths")
@click.argument("ini_root")
@click.argument("old_letter")
@click.argument("new_letter")
@click.option("--dry-run", is_flag=True, help="Show changes without writing files")
def drives_rewrite_paths(ini_root, old_letter, new_letter, dry_run):
    """Update drive letter references in all .ini files under INI_ROOT.

    \b
    Example: after moving from D: to E:
      drives rewrite-paths "E:\\Arcade\\RocketLauncher" D E
    """
    from engines.drive_transfer import rewrite_ini_paths

    old = old_letter.upper().strip(":\\")
    new = new_letter.upper().strip(":\\")
    console.print(f"[bold]Scanning {ini_root} for {old}:\\ → {new}:\\ ...[/bold]")

    if dry_run:
        console.print("[yellow](dry-run)[/yellow]")

    result = rewrite_ini_paths(ini_root, old, new, dry_run=dry_run)

    console.print(f"  Scanned: {result['files_scanned']:,} .ini files")
    console.print(f"  Changed: [bold]{result['files_changed']:,}[/bold] files  "
                  f"({result['lines_changed']:,} path references)")

    if dry_run and result["changed_files"]:
        console.print("\n[dim]Would update:[/dim]")
        for f in result["changed_files"][:20]:
            console.print(f"  [dim]{f}[/dim]")


# ---- Plugins ----

@cli.group()
def plugin():
    """Plugin management — discover, enable, disable, create plugins."""
    pass


@plugin.command("list")
@click.option("--all", "show_all", is_flag=True, help="Include unloaded plugins from discovery")
def plugin_list(show_all):
    """List plugins. Shows loaded plugins by default, --all shows discovered too."""
    from plugins import manager as pm

    if show_all:
        found = pm.discover()
        if not found:
            console.print("[dim]No plugins found in plugins/ directory.[/dim]")
            return
        table = Table(title="Available Plugins")
        table.add_column("Name", style="cyan")
        table.add_column("Version")
        table.add_column("Style")
        table.add_column("Author")
        table.add_column("State")
        table.add_column("Description")
        for p in found:
            loaded = pm.get_plugin(p["name"])
            state = loaded.state.name if loaded else "NOT LOADED"
            state_style = {"ENABLED": "[green]ENABLED[/green]", "DISABLED": "[yellow]DISABLED[/yellow]",
                           "ERROR": "[red]ERROR[/red]"}.get(state, f"[dim]{state}[/dim]")
            table.add_row(p["name"], p["version"], p["style"], p.get("author", ""),
                          state_style, p["description"][:60])
        console.print(table)
    else:
        plugins = pm.list_plugins()
        if not plugins:
            console.print("[dim]No plugins loaded. Use 'plugin list --all' to discover, or 'plugin enable <name>'.[/dim]")
            return
        table = Table(title="Loaded Plugins")
        table.add_column("Name", style="cyan")
        table.add_column("Version")
        table.add_column("State")
        table.add_column("Description")
        for p in plugins:
            state = p.get("state", "UNKNOWN")
            state_style = {"ENABLED": "[green]ENABLED[/green]", "DISABLED": "[yellow]DISABLED[/yellow]",
                           "ERROR": "[red]ERROR[/red]"}.get(state, state)
            table.add_row(p["name"], p["version"], state_style, p.get("description", "")[:60])
        console.print(table)


@plugin.command("enable")
@click.argument("name")
def plugin_enable(name):
    """Enable a plugin (loads it first if needed)."""
    from plugins import manager as pm
    if pm.enable(name):
        console.print(f"[green]✓[/green] Plugin '{name}' enabled")
    else:
        p = pm.get_plugin(name)
        err = p._error if p else "file not found"
        console.print(f"[red]✗[/red] Failed to enable plugin '{name}': {err}")


@plugin.command("disable")
@click.argument("name")
def plugin_disable(name):
    """Disable an enabled plugin."""
    from plugins import manager as pm
    if pm.disable(name):
        console.print(f"[green]✓[/green] Plugin '{name}' disabled")
    else:
        console.print(f"[red]✗[/red] Could not disable '{name}' (dependency conflict or not loaded)")


@plugin.command("unload")
@click.argument("name")
def plugin_unload(name):
    """Unload a plugin from memory."""
    from plugins import manager as pm
    if pm.unload(name):
        console.print(f"[green]✓[/green] Plugin '{name}' unloaded")
    else:
        console.print(f"[red]✗[/red] Could not unload '{name}'")


@plugin.command("info")
@click.argument("name")
def plugin_info(name):
    """Show detailed info about a plugin."""
    from plugins import manager as pm

    # Try loaded first, then discover
    p = pm.get_plugin(name)
    if p:
        info = p.to_dict()
        table = Table(title=f"Plugin: {info['name']}")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("Name", info["name"])
        table.add_row("Version", info["version"])
        table.add_row("Description", info.get("description", ""))
        table.add_row("Author", info.get("author", ""))
        table.add_row("License", info.get("license", ""))
        table.add_row("State", info["state"])
        table.add_row("Tags", ", ".join(info.get("tags", [])) or "none")
        table.add_row("Dependencies", ", ".join(info.get("dependencies", [])) or "none")
        if info.get("error"):
            table.add_row("Error", f"[red]{info['error']}[/red]")
        status = info.get("status", {})
        for k, v in status.items():
            if k not in ("name", "version", "state", "error"):
                table.add_row(f"status.{k}", str(v))
        console.print(table)
    else:
        # Check if discoverable
        for d in pm.discover():
            if d["name"] == name:
                console.print(f"Plugin '{name}' found but not loaded. Use 'plugin enable {name}' first.")
                console.print(f"  Style: {d['style']}, Version: {d['version']}")
                return
        console.print(f"[red]Plugin '{name}' not found.[/red]")


@plugin.command("create")
@click.argument("name")
@click.option("--author", "-a", default="", help="Author name")
def plugin_create(name, author):
    """Create a new plugin scaffold from template."""
    from plugins import manager as pm
    try:
        path = pm.create_plugin_scaffold(name, author)
        console.print(f"[green]✓[/green] Plugin scaffold created: {path}")
        console.print(f"[dim]Edit the file and run 'plugin enable {name}' to activate.[/dim]")
    except FileExistsError as exc:
        console.print(f"[red]✗[/red] {exc}")


@plugin.command("events")
def plugin_events():
    """Show active event bus subscriptions."""
    from plugins import manager as pm
    events = pm.event_bus.list_events()
    if not events:
        console.print("[dim]No active event subscriptions.[/dim]")
        return
    table = Table(title="Event Bus Subscriptions")
    table.add_column("Event", style="cyan")
    table.add_column("Listeners", justify="right")
    for e in sorted(events):
        table.add_row(e, str(pm.event_bus.listener_count(e)))
    console.print(table)
    console.print(f"\n[dim]Total: {len(events)} events, "
                  f"{sum(pm.event_bus.listener_count(e) for e in events)} listeners[/dim]")


@plugin.command("load-all")
def plugin_load_all():
    """Discover and enable all available plugins."""
    from plugins import manager as pm
    pm.load_all()
    results = pm.enable_all()
    ok = sum(1 for v in results.values() if v)
    fail = sum(1 for v in results.values() if not v)
    console.print(f"[green]✓[/green] {ok} plugins enabled, {fail} failed")
    for name, success in results.items():
        icon = "[green]✓[/green]" if success else "[red]✗[/red]"
        console.print(f"  {icon} {name}")


if __name__ == "__main__":
    # Fix Click command name for subgroups
    cli.add_command(audit_cmd, "audit")
    cli()
