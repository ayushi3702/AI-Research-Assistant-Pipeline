"""
Persistent audit logging.

Writes a structured record to BOTH:
  1. The `audit_logs` database table  (queryable via the API for support)
  2. A rotating file on disk          (logs/audit.log — survives restarts)

Designed to never raise: audit failures must not break the pipeline.
"""
from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler

from shared.database import SessionLocal, AuditLog

# ── File logging setup ────────────────────────────────────────────────────────

LOG_DIR = os.getenv("LOG_DIR", "/app/logs" if os.path.isdir("/app") else "./logs")

# Supported severity levels (low → high). Anything else falls back to "info".
LEVELS = ("info", "warning", "error")

_LEVEL_TO_LOGGING = {
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

_audit_file_logger: logging.Logger | None = None


def _get_file_logger() -> logging.Logger:
    """Lazily create a dedicated rotating-file logger for audit events."""
    global _audit_file_logger
    if _audit_file_logger is not None:
        return _audit_file_logger

    logger = logging.getLogger("audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "audit.log"),
            maxBytes=5 * 1024 * 1024,   # 5 MB per file
            backupCount=10,             # keep ~50 MB of history
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
        # Avoid duplicate handlers on re-import
        if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
            logger.addHandler(handler)
    except Exception:
        # If the file system isn't writable, fall back to console only.
        pass

    _audit_file_logger = logger
    return logger


# ── Public API ────────────────────────────────────────────────────────────────

def audit(
    event: str,
    *,
    level: str = "info",
    job_id: str | None = None,
    user_id: str | None = None,
    agent: str | None = None,
    message: str = "",
    detail: str | dict | None = None,
) -> None:
    """
    Record an audit event. Persists to the DB and a rotating log file.

    event   — machine-readable event name, e.g. "job_failed", "agent_failed".
    level   — "info" | "warning" | "error".
    detail  — free-form string or dict (e.g. a traceback); dicts are JSON-encoded.
    """
    level = level if level in LEVELS else "info"

    if isinstance(detail, dict):
        detail_str = json.dumps(detail, default=str)
    else:
        detail_str = detail

    # 1) File log (best-effort) — write at the matching severity
    try:
        line = json.dumps(
            {
                "level": level,
                "event": event,
                "job_id": job_id,
                "user_id": user_id,
                "agent": agent,
                "message": message,
                "detail": detail_str,
            },
            default=str,
        )
        _get_file_logger().log(_LEVEL_TO_LOGGING[level], line)
    except Exception:
        pass

    # 2) Database (best-effort)
    db = None
    try:
        db = SessionLocal()
        db.add(
            AuditLog(
                job_id=job_id,
                user_id=user_id,
                level=level,
                event=event,
                agent=agent,
                message=message[:2000] if message else message,
                detail=detail_str,
            )
        )
        db.commit()
    except Exception:
        pass
    finally:
        if db is not None:
            db.close()
