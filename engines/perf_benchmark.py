"""
M32 -- Performance Benchmarking for Emulators

Provides:
  - Benchmark emulator launch times
  - Track performance per game/emulator combo
  - Recommend optimal emulator per system
  - Performance history over time
  - SQLite persistent storage for benchmark results
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("perf_benchmark")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "perf_benchmarks.db"


@dataclass
class BenchmarkResult:
    """Single benchmark measurement."""
    bench_id: int = 0
    emulator: str = ""
    system: str = ""
    game: str = ""
    launch_time_ms: float = 0
    cpu_usage_pct: float = 0
    memory_mb: float = 0
    fps_avg: float = 0
    score: float = 0        # composite 0-100
    timestamp: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EmulatorRanking:
    """Ranking of emulators for a system."""
    system: str
    rankings: List[Dict[str, Any]] = field(default_factory=list)
    recommended: str = ""
    sample_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------
# SQLite
# -----------------------------------------------------------------------

def _ensure_db() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS benchmarks (
            bench_id INTEGER PRIMARY KEY AUTOINCREMENT,
            emulator TEXT NOT NULL,
            system TEXT NOT NULL,
            game TEXT DEFAULT '',
            launch_time_ms REAL DEFAULT 0,
            cpu_usage_pct REAL DEFAULT 0,
            memory_mb REAL DEFAULT 0,
            fps_avg REAL DEFAULT 0,
            score REAL DEFAULT 0,
            timestamp TEXT NOT NULL,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS emulator_paths (
            emulator TEXT NOT NULL,
            exe_path TEXT NOT NULL,
            system TEXT DEFAULT '',
            args_template TEXT DEFAULT '',
            PRIMARY KEY (emulator, system)
        );

        CREATE INDEX IF NOT EXISTS idx_bench_emu ON benchmarks(emulator);
        CREATE INDEX IF NOT EXISTS idx_bench_sys ON benchmarks(system);
        CREATE INDEX IF NOT EXISTS idx_bench_ts ON benchmarks(timestamp);
    """)
    conn.commit()
    return conn


# -----------------------------------------------------------------------
# Emulator path management
# -----------------------------------------------------------------------

def register_emulator(emulator: str, exe_path: str, system: str = "",
                      args_template: str = "") -> Dict[str, Any]:
    """Register an emulator executable for benchmarking.

    Args:
        emulator: Emulator name
        exe_path: Path to executable
        system: System this config is for
        args_template: Command line template ({rom} placeholder)
    """
    conn = _ensure_db()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO emulator_paths (emulator, exe_path, system, args_template)
            VALUES (?,?,?,?)
        """, (emulator, exe_path, system, args_template))
        conn.commit()
        return {"emulator": emulator, "exe_path": exe_path, "system": system, "registered": True}
    finally:
        conn.close()


def list_registered_emulators() -> Dict[str, Any]:
    """List all registered emulators."""
    conn = _ensure_db()
    try:
        rows = conn.execute("SELECT * FROM emulator_paths ORDER BY emulator").fetchall()
        return {
            "emulators": [
                {"emulator": r[0], "exe_path": r[1], "system": r[2], "args_template": r[3]}
                for r in rows
            ],
            "count": len(rows),
        }
    finally:
        conn.close()


# -----------------------------------------------------------------------
# Benchmarking
# -----------------------------------------------------------------------

def benchmark_launch(emulator: str, exe_path: str = "",
                     system: str = "", game: str = "",
                     rom_path: str = "", timeout: int = 30) -> Dict[str, Any]:
    """Benchmark emulator launch time.

    Args:
        emulator: Emulator name
        exe_path: Path to emulator executable (or auto-detect from registry)
        system: System name
        game: Game name for record keeping
        rom_path: Optional ROM to load
        timeout: Seconds to wait before killing process

    Returns:
        Benchmark result
    """
    # Resolve exe path
    if not exe_path:
        conn = _ensure_db()
        try:
            row = conn.execute(
                "SELECT exe_path, args_template FROM emulator_paths WHERE emulator=? AND (system=? OR system='') LIMIT 1",
                (emulator, system)
            ).fetchone()
            if row:
                exe_path = row[0]
        finally:
            conn.close()

    if not exe_path or not Path(exe_path).exists():
        return {"error": f"Emulator executable not found: {exe_path or emulator}"}

    # Build command
    cmd = [exe_path]
    if rom_path:
        cmd.append(rom_path)

    # Measure launch time
    start = time.perf_counter()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        # Wait briefly to measure startup
        try:
            proc.wait(timeout=min(timeout, 10))
        except subprocess.TimeoutExpired:
            pass

        launch_ms = (time.perf_counter() - start) * 1000

        # Try to get memory usage
        memory_mb = 0.0
        try:
            import psutil
            p = psutil.Process(proc.pid)
            mem_info = p.memory_info()
            memory_mb = mem_info.rss / (1024 * 1024)
        except Exception:
            pass

        # Kill the process if still running
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    except FileNotFoundError:
        return {"error": f"Emulator not found: {exe_path}"}
    except Exception as e:
        return {"error": f"Benchmark failed: {e}"}

    # Calculate score (lower launch time = higher score)
    score = max(0, 100 - (launch_ms / 100))  # 0ms=100, 10s=0

    result = BenchmarkResult(
        emulator=emulator,
        system=system,
        game=game,
        launch_time_ms=round(launch_ms, 1),
        memory_mb=round(memory_mb, 1),
        score=round(score, 1),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Save to DB
    _save_benchmark(result)

    return result.to_dict()


def record_benchmark(emulator: str, system: str = "", game: str = "",
                     launch_time_ms: float = 0, cpu_usage_pct: float = 0,
                     memory_mb: float = 0, fps_avg: float = 0,
                     notes: str = "") -> Dict[str, Any]:
    """Manually record a benchmark result.

    Args:
        emulator: Emulator name
        system: System name
        game: Game name
        launch_time_ms: Launch time in milliseconds
        cpu_usage_pct: CPU usage percentage
        memory_mb: Memory usage in MB
        fps_avg: Average FPS
        notes: Additional notes

    Returns:
        Recorded benchmark
    """
    # Composite score
    score = 50.0
    if launch_time_ms > 0:
        score += max(-25, 25 - (launch_time_ms / 400))
    if fps_avg > 0:
        score += min(25, (fps_avg / 60) * 25)
    if memory_mb > 0:
        score -= min(15, memory_mb / 200)
    if cpu_usage_pct > 0:
        score -= min(10, cpu_usage_pct / 10)
    score = max(0, min(100, score))

    result = BenchmarkResult(
        emulator=emulator, system=system, game=game,
        launch_time_ms=launch_time_ms, cpu_usage_pct=cpu_usage_pct,
        memory_mb=memory_mb, fps_avg=fps_avg, score=round(score, 1),
        timestamp=datetime.now(timezone.utc).isoformat(), notes=notes,
    )

    _save_benchmark(result)
    return result.to_dict()


def _save_benchmark(result: BenchmarkResult):
    conn = _ensure_db()
    try:
        conn.execute("""
            INSERT INTO benchmarks
            (emulator, system, game, launch_time_ms, cpu_usage_pct,
             memory_mb, fps_avg, score, timestamp, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (result.emulator, result.system, result.game,
              result.launch_time_ms, result.cpu_usage_pct,
              result.memory_mb, result.fps_avg, result.score,
              result.timestamp, result.notes))
        conn.commit()
    finally:
        conn.close()


# -----------------------------------------------------------------------
# Queries & Rankings
# -----------------------------------------------------------------------

def get_benchmarks(emulator: str = "", system: str = "",
                   limit: int = 50) -> Dict[str, Any]:
    """Get benchmark results with optional filters."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM benchmarks WHERE 1=1"
        params: list = []
        if emulator:
            sql += " AND emulator=?"
            params.append(emulator)
        if system:
            sql += " AND system=?"
            params.append(system)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM benchmarks LIMIT 0").description]
        return {
            "benchmarks": [dict(zip(cols, r)) for r in rows],
            "count": len(rows),
        }
    finally:
        conn.close()


def rank_emulators(system: str) -> Dict[str, Any]:
    """Rank emulators for a system based on average benchmark scores.

    Args:
        system: System to rank emulators for

    Returns:
        Ranked emulator list with recommendation
    """
    conn = _ensure_db()
    try:
        rows = conn.execute("""
            SELECT emulator,
                   AVG(score) as avg_score,
                   AVG(launch_time_ms) as avg_launch,
                   AVG(memory_mb) as avg_memory,
                   AVG(fps_avg) as avg_fps,
                   COUNT(*) as samples
            FROM benchmarks
            WHERE system=?
            GROUP BY emulator
            ORDER BY avg_score DESC
        """, (system,)).fetchall()

        if not rows:
            return {"system": system, "rankings": [], "message": "No benchmarks for this system"}

        rankings = []
        for r in rows:
            rankings.append({
                "emulator": r[0],
                "avg_score": round(r[1], 1),
                "avg_launch_ms": round(r[2], 1),
                "avg_memory_mb": round(r[3], 1),
                "avg_fps": round(r[4], 1) if r[4] else 0,
                "samples": r[5],
            })

        result = EmulatorRanking(
            system=system,
            rankings=rankings,
            recommended=rankings[0]["emulator"] if rankings else "",
            sample_size=sum(r["samples"] for r in rankings),
        )
        return result.to_dict()
    finally:
        conn.close()


def performance_history(emulator: str, system: str = "",
                        limit: int = 30) -> Dict[str, Any]:
    """Get performance history for an emulator over time."""
    conn = _ensure_db()
    try:
        sql = "SELECT timestamp, score, launch_time_ms, memory_mb, fps_avg FROM benchmarks WHERE emulator=?"
        params: list = [emulator]
        if system:
            sql += " AND system=?"
            params.append(system)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return {
            "emulator": emulator,
            "system": system,
            "history": [
                {"timestamp": r[0], "score": r[1], "launch_ms": r[2],
                 "memory_mb": r[3], "fps": r[4]}
                for r in rows
            ],
            "count": len(rows),
        }
    finally:
        conn.close()


def benchmark_summary() -> Dict[str, Any]:
    """Get overall benchmark summary across all systems."""
    conn = _ensure_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM benchmarks").fetchone()[0]
        systems = conn.execute("SELECT DISTINCT system FROM benchmarks ORDER BY system").fetchall()
        emulators = conn.execute("SELECT DISTINCT emulator FROM benchmarks ORDER BY emulator").fetchall()

        per_system = []
        for (sys_name,) in systems:
            row = conn.execute("""
                SELECT emulator, AVG(score) as avg
                FROM benchmarks WHERE system=?
                GROUP BY emulator ORDER BY avg DESC LIMIT 1
            """, (sys_name,)).fetchone()
            per_system.append({
                "system": sys_name,
                "best_emulator": row[0] if row else "",
                "best_score": round(row[1], 1) if row else 0,
            })

        return {
            "total_benchmarks": total,
            "systems_tested": len(systems),
            "emulators_tested": len(emulators),
            "emulator_list": [e[0] for e in emulators],
            "per_system": per_system,
        }
    finally:
        conn.close()


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python perf_benchmark.py launch <emulator> <exe_path> [system]")
        print("  python perf_benchmark.py rank <system>")
        print("  python perf_benchmark.py summary")
        print("  python perf_benchmark.py history <emulator> [system]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "launch":
        emu = sys.argv[2] if len(sys.argv) > 2 else ""
        exe = sys.argv[3] if len(sys.argv) > 3 else ""
        sys_name = sys.argv[4] if len(sys.argv) > 4 else ""
        result = benchmark_launch(emu, exe, sys_name)
        print(json.dumps(result, indent=2))

    elif cmd == "rank":
        sys_name = sys.argv[2] if len(sys.argv) > 2 else ""
        result = rank_emulators(sys_name)
        print(json.dumps(result, indent=2))

    elif cmd == "summary":
        result = benchmark_summary()
        print(json.dumps(result, indent=2))

    elif cmd == "history":
        emu = sys.argv[2] if len(sys.argv) > 2 else ""
        sys_name = sys.argv[3] if len(sys.argv) > 3 else ""
        result = performance_history(emu, sys_name)
        print(json.dumps(result, indent=2))
