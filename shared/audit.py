"""
Structured business-event audit log.

Persists audit events (job lifecycle, agent failures, warnings) to the
`audit_logs` database table, queryable via the API for support/diagnostics.

NOTE: This is intentionally DB-only. Free-form diagnostic logging
(logger.info / warning / error from across the codebase) goes to the
application log file via `shared.logging_config` — not here.

Designed to never raise: audit failures must not break the pipeline.
"""
from __future__ import annotations

import json
import logging

from shared.database import SessionLocal, AuditLog

logger = logging.getLogger(__name__)

# Supported severity levels. Anything else falls back to "info".
LEVELS = ("info", "warning", "error")


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
    Record a structured audit event in the database.

    event   — machine-readable event name, e.g. "job_failed", "agent_failed".
    level   — "info" | "warning" | "error".
    detail  — free-form string or dict (e.g. a traceback); dicts are JSON-encoded.
    """
    level = level if level in LEVELS else "info"

    if isinstance(detail, dict):
        detail_str = json.dumps(detail, default=str)
    else:
        detail_str = detail

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
        # Never let audit persistence break the caller; log it to the app log.
        logger.error("Failed to persist audit event %r", event, exc_info=True)
    finally:
        if db is not None:
            db.close()
