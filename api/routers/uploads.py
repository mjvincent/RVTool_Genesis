"""Uploads router — /api/projects/{project_id}/uploads + records."""
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Assumption, ServerRecord, Upload
from routers.projects import _get_project_or_404
from schemas.upload import RecordsListResponse, ServerRecordResponse, UploadResponse
from services.spreadsheet_parser import ALLOWED_EXTENSIONS, parse_spreadsheet

logger = logging.getLogger(__name__)

router = APIRouter(tags=["uploads"])

_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Upload endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Accept a multipart spreadsheet upload, parse it, and store server records."""
    await _get_project_or_404(db, project_id)

    # --- Validate file type ---------------------------------------------------
    filename = file.filename or "upload"
    lower = filename.lower()
    ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    # --- Read bytes -----------------------------------------------------------
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"File exceeds 50 MB limit "
                f"(received {len(file_bytes) / 1024 / 1024:.1f} MB)"
            ),
        )

    # --- Create Upload record (status=processing) ----------------------------
    upload = Upload(
        project_id=project_id,
        filename=filename,
        raw_file=file_bytes,
        status="processing",
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)

    # --- Parse ----------------------------------------------------------------
    try:
        rows = await asyncio.to_thread(parse_spreadsheet, file_bytes, filename)
    except ValueError as exc:
        upload.status = "error"
        upload.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error parsing '%s'", filename)
        upload.status = "error"
        upload.error_message = f"Parsing failed: {exc}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parsing failed: {exc}",
        ) from exc

    # --- Persist server records -----------------------------------------------
    for row in rows:
        record = ServerRecord(
            upload_id=upload.id,
            project_id=project_id,
            raw_data=row,
            normalized_data=None,
            processing_status="pending",
        )
        db.add(record)

    upload.status = "complete"
    upload.row_count = len(rows)
    await db.commit()
    await db.refresh(upload)

    return UploadResponse.model_validate(upload)


@router.get(
    "/projects/{project_id}/uploads",
    response_model=list[UploadResponse],
)
async def list_uploads(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[UploadResponse]:
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(Upload)
        .where(Upload.project_id == project_id)
        .order_by(Upload.uploaded_at.desc())
    )
    uploads = result.scalars().all()
    return [UploadResponse.model_validate(u) for u in uploads]


@router.get(
    "/projects/{project_id}/uploads/{upload_id}",
    response_model=UploadResponse,
)
async def get_upload(
    project_id: uuid.UUID,
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    await _get_project_or_404(db, project_id)
    upload = await _get_upload_or_404(db, project_id, upload_id)
    return UploadResponse.model_validate(upload)


# ---------------------------------------------------------------------------
# Server records endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/records",
    response_model=RecordsListResponse,
)
async def list_records(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RecordsListResponse:
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(ServerRecord)
        .where(ServerRecord.project_id == project_id)
        .order_by(ServerRecord.created_at.asc())
    )
    records = result.scalars().all()
    return RecordsListResponse(
        records=[ServerRecordResponse.model_validate(r) for r in records],
        total=len(records),
    )


@router.get(
    "/projects/{project_id}/records/{record_id}",
    response_model=ServerRecordResponse,
)
async def get_record(
    project_id: uuid.UUID,
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ServerRecordResponse:
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
    return ServerRecordResponse.model_validate(record)


@router.patch(
    "/projects/{project_id}/records/{record_id}",
    response_model=ServerRecordResponse,
)
async def patch_record(
    project_id: uuid.UUID,
    record_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> ServerRecordResponse:
    """Partially update a normalized server record's vinfo fields.

    Accepts a flat dict of vinfo field overrides (e.g. {"vm_name": "new-name", "cpus": 4}).
    Merges them into the existing normalized_data.vinfo without touching other sub-keys.
    """
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

    if not record.normalized_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Record has not been normalized yet",
        )

    import copy
    updated = copy.deepcopy(record.normalized_data)

    # Accept top-level vinfo overrides
    vinfo_overrides = body.get("vinfo", body)  # support both {"vinfo": {...}} and flat dict
    if not isinstance(vinfo_overrides, dict):
        raise HTTPException(status_code=422, detail="Body must be a JSON object")

    updated.setdefault("vinfo", {}).update(vinfo_overrides)
    record.normalized_data = updated

    await db.commit()
    await db.refresh(record)
    return ServerRecordResponse.model_validate(record)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_upload_or_404(
    db: AsyncSession, project_id: uuid.UUID, upload_id: uuid.UUID
) -> Upload:
    result = await db.execute(
        select(Upload).where(
            Upload.id == upload_id,
            Upload.project_id == project_id,
        )
    )
    upload = result.scalar_one_or_none()
    if upload is None:
        raise HTTPException(status_code=404, detail=f"Upload {upload_id} not found")
    return upload


# ---------------------------------------------------------------------------
# Assumptions endpoint
# ---------------------------------------------------------------------------

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


@router.get(
    "/projects/{project_id}/assumptions",
    response_model=AssumptionsListResponse,
)
async def list_assumptions(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AssumptionsListResponse:
    """Return all AI-generated assumptions for every record in a project."""
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(Assumption)
        .where(Assumption.project_id == project_id)
        .order_by(Assumption.created_at.asc())
    )
    assumptions = result.scalars().all()
    return AssumptionsListResponse(
        assumptions=[AssumptionResponse.model_validate(a) for a in assumptions],
        total=len(assumptions),
    )
