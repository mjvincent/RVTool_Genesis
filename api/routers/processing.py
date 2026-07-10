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
from db.models import Assumption, ServerRecord
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
            record.normalized_data = {
                "vinfo": normalized.get("vinfo", {}),
                "vnetwork": normalized.get("vnetwork", []),
                "vpartition": normalized.get("vpartition", []),
                "vhost": normalized.get("vhost", {}),
            }
            record.server_type = normalized.get("server_type")
            record.processing_status = "complete"
            record.error_message = None

            # Persist assumption rows (delete any stale ones first)
            stale = await db.execute(
                select(Assumption).where(Assumption.server_record_id == record_id)
            )
            for old in stale.scalars().all():
                await db.delete(old)

            for assumption_data in normalized.get("assumptions", []):
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

    return ProcessingStatusResponse(
        total=total,
        pending=pending,
        processing=processing,
        complete=complete,
        error=error,
        is_complete=(total > 0 and pending == 0 and processing == 0),
    )


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
