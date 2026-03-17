"""Structured logging and audit trail for the HyperSpin Extreme Toolkit."""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import get as cfg_get


_loggers: dict[str, logging.Logger] = {}
_audit_path: Path | None = None


class JsonFormatter(logging.Formatter):
    """Emit structured JSON log lines."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_data", None)
        if extra:
            entry["data"] = extra
        return json.dumps(entry, default=str)


def _log_dir() -> Path:
    d = Path(cfg_get("paths.logs_dir", "logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with file + console handlers."""
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(f"hstk.{name}")
    level_str = cfg_get("logging.level", "INFO").upper()
    logger.setLevel(getattr(logging, level_str, logging.INFO))

    if not logger.handlers:
        # Console handler (human-readable)
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(ch)

        # File handler (JSON, rotating)
        max_bytes = int(cfg_get("logging.max_file_size_mb", 50)) * 1024 * 1024
        max_files = int(cfg_get("logging.max_files", 10))
        log_file = _log_dir() / f"{name}.log"
        fh = logging.handlers.RotatingFileHandler(
            str(log_file), maxBytes=max_bytes, backupCount=max_files, encoding="utf-8"
        )
        use_json = cfg_get("logging.json_format", True)
        if use_json:
            fh.setFormatter(JsonFormatter())
        else:
            fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
        logger.addHandler(fh)

    _loggers[name] = logger
    return logger


def audit(action: str, target: str, details: dict[str, Any] | None = None, user: str = "system") -> None:
    """Write a tamper-evident audit trail entry."""
    global _audit_path
    if _audit_path is None:
        _audit_path = _log_dir() / "audit_trail.jsonl"

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "target": target,
        "user": user,
        "details": details or {},
        "pid": os.getpid(),
    }
    with open(_audit_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
