"""Processing router — AI normalization endpoints."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import AsyncSessionLocal, get_db
from db.models import Assumption, AuditLog, ServerRecord
from routers.projects import _get_project_or_404
from services import ai_normalizer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["processing"])


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class ProcessStartResponse(BaseModel):
    status: str
    record_count: int
    message: str


class ProcessingStatusResponse(BaseModel):
    total: int
    pending: int
    processing: int
    complete: int
    error: int
    is_complete: bool
    current_record_name: str | None = None


class AssumptionResponse(BaseModel):
    id: uuid.UUID
    server_record_id: uuid.UUID
    project_id: uuid.UUID
    field_name: str
    assumed_value: str
    original_value: str | None
    reasoning: str
    confidence: str

    class Config:
        from_attributes = True


class AssumptionsListResponse(BaseModel):
    assumptions: list[AssumptionResponse]
    total: int


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

_BATCH_SIZE = 1        # Serial: Ollama is single-model, concurrent calls just queue and timeout
_BATCH_DELAY_SECONDS = 0.5


async def _process_single_record(record_id: uuid.UUID, project_id: uuid.UUID) -> None:
    """Process one ServerRecord: call Claude, persist results, create Assumption rows."""
    async with AsyncSessionLocal() as db:
        # Fetch record
        result = await db.execute(
            select(ServerRecord).where(ServerRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            logger.warning("Record %s not found, skipping", record_id)
            return

        record.processing_status = "processing"
        await db.commit()

        try:
            # Run synchronous Claude call in a thread to avoid blocking the event loop
            normalized = await asyncio.to_thread(
                ai_normalizer.normalize_record, record.raw_data
            )

            # Persist normalized data on the record
            vinfo = normalized.get("vinfo") or {}
            record.normalized_data = {
                "vinfo": vinfo,
                "vnetwork": normalized.get("vnetwork", []),
                "vpartition": normalized.get("vpartition", []),
                "vhost": normalized.get("vhost", {}),
            }
            record.server_type = normalized.get("server_type")

            # Sub-Task F: validate that LLM returned meaningful vinfo content.
            # An empty vinfo ({}) or one missing all three anchor fields produces
            # blank export rows — mark as error so the user can fix it manually.
            _anchor_fields = ("vm_name", "num_cpus", "cpus", "memory_mb", "memory")
            if not vinfo or not any(vinfo.get(f) for f in _anchor_fields):
                record.processing_status = "error"
                record.error_message = (
                    "AI response missing required fields (vm_name, cpus, memory_mb). "
                    "Use Edit & fix to complete this record manually."
                )
            else:
                record.processing_status = "complete"
                record.error_message = None

            # Persist assumption rows (delete any stale ones first)
            stale = await db.execute(
                select(Assumption).where(Assumption.server_record_id == record_id)
            )
            for old in stale.scalars().all():
                await db.delete(old)

            for assumption_data in normalized.get("assumptions", []):
                # Guard: LLM occasionally returns strings instead of dicts in
                # the assumptions list — skip anything that isn't a mapping.
                if not isinstance(assumption_data, dict):
                    logger.warning(
                        "Skipping non-dict assumption item for record %s: %r",
                        record_id, assumption_data
                    )
                    continue
                assumption = Assumption(
                    server_record_id=record_id,
                    project_id=project_id,
                    field_name=str(assumption_data.get("field_name", "")),
                    assumed_value=str(assumption_data.get("assumed_value", "")),
                    original_value=(
                        str(assumption_data["original_value"])
                        if assumption_data.get("original_value") is not None
                        else None
                    ),
                    reasoning=str(assumption_data.get("reasoning", "")),
                    confidence=str(assumption_data.get("confidence", "low")),
                )
                db.add(assumption)

            await db.commit()
            logger.info("Record %s processed successfully", record_id)

        except Exception as exc:
            logger.exception("Error processing record %s", record_id)
            record.processing_status = "error"
            record.error_message = str(exc)
            await db.commit()


async def process_all_records(
    project_id: uuid.UUID,
    record_ids: list[uuid.UUID],
) -> None:
    """Process records one at a time — Ollama is serial, concurrency just causes timeouts."""
    total = len(record_ids)
    logger.info("Starting background processing of %d records for project %s", total, project_id)

    for record_id in record_ids:
        await _process_single_record(record_id, project_id)
        await asyncio.sleep(_BATCH_DELAY_SECONDS)

    logger.info("Background processing complete for project %s", project_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/process",
    response_model=ProcessStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_processing(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ProcessStartResponse:
    """Trigger AI normalization for all pending records in a project."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "pending",
        )
    )
    pending_records = result.scalars().all()

    if not pending_records:
        return ProcessStartResponse(
            status="no_pending_records",
            record_count=0,
            message="No pending records found for this project",
        )

    record_ids = [r.id for r in pending_records]

    # Do NOT bulk pre-mark as processing — each record is marked individually
    # when its turn comes, so the progress counter increments correctly.
    background_tasks.add_task(process_all_records, project_id, record_ids)

    return ProcessStartResponse(
        status="started",
        record_count=len(record_ids),
        message=f"Processing {len(record_ids)} records in background",
    )


@router.get(
    "/projects/{project_id}/processing-status",
    response_model=ProcessingStatusResponse,
)
async def get_processing_status(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProcessingStatusResponse:
    """Return live counts of records by processing_status for a project."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(ServerRecord.processing_status, func.count(ServerRecord.id))
        .where(ServerRecord.project_id == project_id)
        .group_by(ServerRecord.processing_status)
    )
    counts: dict[str, int] = {row[0]: row[1] for row in result.all()}

    total = sum(counts.values())
    pending = counts.get("pending", 0)
    processing = counts.get("processing", 0)
    complete = counts.get("complete", 0)
    error = counts.get("error", 0)

    # Best-effort: find the VM name of the record currently being processed
    current_record_name: str | None = None
    if processing > 0:
        in_flight = await db.execute(
            select(ServerRecord)
            .where(
                ServerRecord.project_id == project_id,
                ServerRecord.processing_status == "processing",
            )
            .limit(1)
        )
        in_flight_record = in_flight.scalar_one_or_none()
        if in_flight_record:
            vinfo = (in_flight_record.normalized_data or {}).get("vinfo") or {}
            raw   = (in_flight_record.raw_data or {}).get("Name") \
                    or (in_flight_record.raw_data or {}).get("VM") \
                    or (in_flight_record.raw_data or {}).get("name")
            current_record_name = vinfo.get("vm_name") or raw or str(in_flight_record.id)

    return ProcessingStatusResponse(
        total=total,
        pending=pending,
        processing=processing,
        complete=complete,
        error=error,
        is_complete=(total > 0 and pending == 0 and processing == 0),
        current_record_name=current_record_name,
    )


# ---------------------------------------------------------------------------
# Migration Readiness Summary
# ---------------------------------------------------------------------------

class ReadinessSummary(BaseModel):
    total: int
    complete_x86: int
    complete_powervs: int
    excluded: int
    error: int
    pending: int
    export_ready: bool   # True when complete_x86 > 0 and error == 0


@router.get(
    "/projects/{project_id}/readiness-summary",
    response_model=ReadinessSummary,
)
async def get_readiness_summary(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ReadinessSummary:
    """Return a single-call migration readiness summary for the Export page banner."""
    await _get_project_or_404(db, project_id)

    # One query: count by (processing_status, is_excluded, server_type)
    rows = await db.execute(
        select(
            ServerRecord.processing_status,
            ServerRecord.is_excluded,
            ServerRecord.server_type,
            func.count(ServerRecord.id).label("n"),
        )
        .where(ServerRecord.project_id == project_id)
        .group_by(
            ServerRecord.processing_status,
            ServerRecord.is_excluded,
            ServerRecord.server_type,
        )
    )

    total = complete_x86 = complete_powervs = excluded = error = pending = 0

    for proc_status, is_excl, srv_type, n in rows.all():
        total += n
        if is_excl:
            excluded += n
            continue
        if proc_status == "complete":
            if srv_type == "powervs":
                complete_powervs += n
            else:
                complete_x86 += n
        elif proc_status == "error":
            error += n
        elif proc_status in ("pending", "processing"):
            pending += n

    return ReadinessSummary(
        total=total,
        complete_x86=complete_x86,
        complete_powervs=complete_powervs,
        excluded=excluded,
        error=error,
        pending=pending,
        export_ready=(complete_x86 > 0 and error == 0),
    )


# ---------------------------------------------------------------------------
# Audit log endpoint
# ---------------------------------------------------------------------------

class AuditLogEntry(BaseModel):
    id: str
    operation: str
    summary: str
    record_count: int | None
    created_at: str


@router.get(
    "/projects/{project_id}/audit-log",
    response_model=list[AuditLogEntry],
)
async def get_audit_log(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogEntry]:
    """Return the 50 most recent audit log entries for a project."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.project_id == project_id)
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    )
    entries = result.scalars().all()
    return [
        AuditLogEntry(
            id=str(e.id),
            operation=e.operation,
            summary=e.summary,
            record_count=e.record_count,
            created_at=e.created_at.isoformat(),
        )
        for e in entries
    ]


@router.post(
    "/projects/{project_id}/records/{record_id}/process",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def process_single_record(
    project_id: uuid.UUID,
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Synchronously process a single record (useful for retrying failed records)."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.id == record_id,
            ServerRecord.project_id == project_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")

    # Reset to pending so it can be re-processed
    record.processing_status = "pending"
    await db.commit()

    # Process synchronously (in thread to avoid blocking the event loop)
    await _process_single_record(record_id, project_id)

    # Reload and return updated record
    await db.refresh(record)
    return {
        "id": str(record.id),
        "processing_status": record.processing_status,
        "server_type": record.server_type,
        "error_message": record.error_message,
    }


@router.post(
    "/projects/{project_id}/processing/reset-stuck",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def reset_stuck_records(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Reset any records stuck in 'processing' state back to 'pending'.

    A record can get stuck if the API container was restarted while a background
    task was running, or if Ollama hung without raising an error.  Call this
    endpoint followed by POST /process to resume.
    """
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "processing",
        )
    )
    stuck = result.scalars().all()
    count = len(stuck)

    for record in stuck:
        record.processing_status = "pending"
        record.error_message = None

    await db.commit()
    logger.info("Reset %d stuck records to pending for project %s", count, project_id)

    return {
        "reset_count": count,
        "message": (
            f"Reset {count} stuck record(s) to pending. "
            "Call POST /projects/{project_id}/process to resume."
        ),
    }
