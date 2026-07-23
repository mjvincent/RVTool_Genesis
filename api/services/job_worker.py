"""PostgreSQL-backed job worker for AI normalization.

Replaces FastAPI BackgroundTasks with a durable queue backed by the existing
PostgreSQL database. No external broker is required.

Design
------
- One ``processing_jobs`` row exists per active or recently-finished job.
- The worker loop polls for ``pending`` jobs using ``SELECT … FOR UPDATE SKIP
  LOCKED`` so that a second API instance (or a concurrent request) cannot claim
  the same job.
- On container crash/restart, ``requeue_stale_jobs()`` is called at startup to
  move any ``in_progress`` job that hasn't been updated within the stale timeout
  back to ``pending`` so the worker picks it up again.
- ``_process_single_record`` lives in ``routers.processing`` (where all its
  imports already are); this module only owns queue mechanics.

Cancellation
------------
Setting ``cancel_requested = True`` on the job row causes the worker to stop
cleanly after the current record finishes.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import AsyncSessionLocal
from db.models import ProcessingJob, ServerRecord

logger = logging.getLogger(__name__)

# How often the worker polls for new pending jobs (seconds)
_POLL_INTERVAL = 2.0

# Delay between records — keeps Ollama from queuing up concurrent calls
_RECORD_DELAY = 0.5

# Jobs in_progress for longer than this at startup are re-queued
STALE_JOB_TIMEOUT_MINUTES = 5


# ---------------------------------------------------------------------------
# Startup re-queue
# ---------------------------------------------------------------------------

async def requeue_stale_jobs() -> int:
    """Re-queue any in_progress jobs that appear to have been orphaned.

    Called once at API startup. Returns the number of jobs re-queued.
    """
    stale_cutoff = datetime.utcnow() - timedelta(minutes=STALE_JOB_TIMEOUT_MINUTES)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProcessingJob).where(
                ProcessingJob.status == "in_progress",
                ProcessingJob.updated_at < stale_cutoff,
            )
        )
        stale = result.scalars().all()
        count = len(stale)
        for job in stale:
            job.status = "pending"
            job.started_at = None
        if count:
            await db.commit()
            logger.warning(
                "Startup recovery: re-queued %d stale processing job(s) "
                "(in_progress for > %d minutes).",
                count, STALE_JOB_TIMEOUT_MINUTES,
            )
        else:
            logger.info("Startup recovery: no stale processing jobs found.")
    return count


# ---------------------------------------------------------------------------
# Job claiming
# ---------------------------------------------------------------------------

async def _claim_next_job(db: AsyncSession) -> ProcessingJob | None:
    """Atomically claim the next pending job.

    Uses SELECT … FOR UPDATE SKIP LOCKED so that:
    - Concurrent workers / requests cannot claim the same job.
    - The claim and status update happen in a single transaction.

    Returns the claimed job (now in_progress) or None if no pending jobs exist.
    """
    result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.status == "pending")
        .order_by(ProcessingJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    job.status = "in_progress"
    job.started_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Record list for a job
# ---------------------------------------------------------------------------

async def _get_pending_record_ids(project_id: uuid.UUID) -> list[uuid.UUID]:
    """Return IDs of all pending ServerRecords for the given project."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ServerRecord.id).where(
                ServerRecord.project_id == project_id,
                ServerRecord.processing_status == "pending",
            )
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------

async def _run_job(job: ProcessingJob) -> None:
    """Execute all pending records for a job, updating progress as we go.

    Imports _process_single_record from routers.processing at call time to
    avoid a circular import at module load.
    """
    from routers.processing import _process_single_record  # noqa: PLC0415

    project_id = job.project_id
    record_ids = await _get_pending_record_ids(project_id)

    if not record_ids:
        # Records may have already been processed (e.g. duplicate start)
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job.id)
                .values(status="done", updated_at=datetime.utcnow())
            )
            await db.commit()
        return

    total = len(record_ids)
    logger.info("Worker: starting job %s — %d records for project %s", job.id, total, project_id)

    # Update total_records on the job row
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job.id)
            .values(total_records=total, updated_at=datetime.utcnow())
        )
        await db.commit()

    for i, record_id in enumerate(record_ids):
        # Check for cancellation before each record
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ProcessingJob.cancel_requested, ProcessingJob.status)
                .where(ProcessingJob.id == job.id)
            )
            row = result.one_or_none()
            if row is None or row.cancel_requested or row.status == "cancelled":
                logger.info("Worker: job %s cancelled — stopping after %d/%d records", job.id, i, total)
                async with AsyncSessionLocal() as db2:
                    await db2.execute(
                        update(ProcessingJob)
                        .where(ProcessingJob.id == job.id)
                        .values(status="cancelled", updated_at=datetime.utcnow())
                    )
                    await db2.commit()
                return

        # Process the record
        await _process_single_record(record_id, project_id)

        # Increment processed counter and heartbeat updated_at
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job.id)
                .values(
                    processed_records=i + 1,
                    updated_at=datetime.utcnow(),
                )
            )
            await db.commit()

        await asyncio.sleep(_RECORD_DELAY)

    # Mark done
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job.id)
            .values(
                status="done",
                processed_records=total,
                updated_at=datetime.utcnow(),
            )
        )
        await db.commit()

    logger.info("Worker: job %s complete — %d records processed for project %s", job.id, total, project_id)


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

async def run_worker_loop() -> None:
    """Long-lived asyncio task: poll for pending jobs and execute them serially.

    Started in the FastAPI lifespan context. Runs until cancelled (on shutdown).
    """
    logger.info("Processing job worker started.")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                job = await _claim_next_job(db)

            if job is not None:
                try:
                    await _run_job(job)
                except Exception:
                    logger.exception("Worker: unhandled error in job %s — marking failed", job.id)
                    async with AsyncSessionLocal() as db:
                        await db.execute(
                            update(ProcessingJob)
                            .where(ProcessingJob.id == job.id)
                            .values(status="failed", updated_at=datetime.utcnow())
                        )
                        await db.commit()
            else:
                # No pending jobs — wait before polling again
                await asyncio.sleep(_POLL_INTERVAL)

        except asyncio.CancelledError:
            logger.info("Processing job worker shutting down.")
            raise
        except Exception:
            logger.exception("Worker: unexpected error in poll loop — retrying in %ds", _POLL_INTERVAL)
            await asyncio.sleep(_POLL_INTERVAL)
