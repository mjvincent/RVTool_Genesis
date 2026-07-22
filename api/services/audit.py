"""Audit logging service — append-only, fire-and-forget."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog

logger = logging.getLogger(__name__)


async def log_audit(
    db: AsyncSession,
    project_id: uuid.UUID,
    operation: str,
    summary: str,
    record_count: int | None = None,
) -> None:
    """Insert one audit log entry.

    Intentionally swallows all exceptions — audit logging must never break
    the primary request path.
    """
    try:
        entry = AuditLog(
            id=uuid.uuid4(),
            project_id=project_id,
            operation=operation,
            summary=summary,
            record_count=record_count,
            created_at=datetime.utcnow(),
        )
        db.add(entry)
        await db.flush()   # write within the caller's transaction; caller commits
    except Exception:  # noqa: BLE001
        logger.warning(
            "audit log write failed for project %s op=%s — suppressed",
            project_id, operation,
        )
