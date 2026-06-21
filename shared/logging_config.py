"""
Centralized application logging.

Configures the root logger so that EVERY module's `logging.getLogger(__name__)`
call streams to:
  1. The console (stdout) — captured by Docker.
  2. A rotating file at <LOG_DIR>/audit.log — survives restarts.

This is the application/diagnostic log (logger.info / warning / error from all
over the codebase). It is separate from the `audit_logs` database table, which
holds structured business events.

Call `configure_logging()` once at each process entry point (API, orchestrator).
It is idempotent and safe to call multiple times.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.getenv("LOG_DIR", "/app/logs" if os.path.isdir("/app") else "./logs")
LOG_FILE = os.path.join(LOG_DIR, "audit.log")

# Default level used when LOG_LEVEL is unset. Override at runtime via the
# LOG_LEVEL application setting (env var / .env / compose) — no code change.
DEFAULT_LOG_LEVEL = "INFO"

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

_configured = False


def _resolve_level(level: str | int | None) -> int:
    """
    Resolve a logging level from an explicit arg or the LOG_LEVEL setting.

    Accepts level names ("DEBUG", "info", ...) or numeric strings/ints
    ("10", 20). Falls back to INFO if the value is missing or invalid.
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)

    if isinstance(level, int):
        return level

    value = str(level).strip().upper()
    if value.isdigit():
        return int(value)

    resolved = logging.getLevelName(value)  # name -> int, or "Level X" string if unknown
    if isinstance(resolved, int):
        return resolved

    return logging.INFO


def configure_logging(level: str | int | None = None) -> None:
    """Attach console + rotating-file handlers to the root logger (idempotent)."""
    global _configured
    if _configured:
        return

    resolved_level = _resolve_level(level)
    root = logging.getLogger()
    root.setLevel(resolved_level)
    formatter = logging.Formatter(_FORMAT)

    # Console handler (skip if one is already present)
    has_stream = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root.handlers
    )
    if not has_stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    # Rotating file handler (best-effort — never crash if FS is read-only)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        has_file = any(isinstance(h, RotatingFileHandler) for h in root.handlers)
        if not has_file:
            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=5 * 1024 * 1024,   # 5 MB per file
                backupCount=10,             # keep ~50 MB of history
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not attach rotating file handler at %s", LOG_FILE, exc_info=True
        )

    _configured = True
