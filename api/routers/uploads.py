"""Uploads router — /api/projects/{project_id}/uploads + records."""
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import delete, select
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

    # --- Delete any existing records and uploads for this project -------------
    # Prevents doubling when user replaces the file: old records in DB must go.
    await db.execute(
        delete(Assumption).where(Assumption.project_id == project_id)
    )
    await db.execute(
        delete(ServerRecord).where(ServerRecord.project_id == project_id)
    )
    # Delete old Upload rows except the one we just created
    old_uploads_result = await db.execute(
        select(Upload).where(
            Upload.project_id == project_id,
            Upload.id != upload.id,
        )
    )
    for old_upload in old_uploads_result.scalars().all():
        await db.delete(old_upload)

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


class ExcludeRecordBody(BaseModel):
    is_excluded: bool
    exclusion_reason: str | None = None


@router.patch(
    "/projects/{project_id}/records/{record_id}/exclude",
    response_model=ServerRecordResponse,
)
async def exclude_record(
    project_id: uuid.UUID,
    record_id: uuid.UUID,
    body: ExcludeRecordBody,
    db: AsyncSession = Depends(get_db),
) -> ServerRecordResponse:
    """Toggle exclusion on a server record and optionally set the reason.

    Excluded records are omitted from all RVTools exports.
    They still appear in the Assumptions Report's 'Excluded Servers' sheet.
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

    record.is_excluded = body.is_excluded
    # Clear reason when un-excluding; preserve when excluding
    if not body.is_excluded:
        record.exclusion_reason = None
    elif body.exclusion_reason is not None:
        record.exclusion_reason = body.exclusion_reason

    await db.commit()
    await db.refresh(record)
    logger.info(
        "Record %s exclusion set to %s (reason: %s)",
        record_id, body.is_excluded, body.exclusion_reason,
    )
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

    If the record's processing_status is 'error' (AI normalization failed), applying a
    manual edit promotes it to 'complete' and clears the error_message so it graduates
    out of the failed-records panel without needing a re-run of the AI.
    """
    import copy

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

    # Accept top-level vinfo overrides
    vinfo_overrides = body.get("vinfo", body)  # support both {"vinfo": {...}} and flat dict
    if not isinstance(vinfo_overrides, dict):
        raise HTTPException(status_code=422, detail="Body must be a JSON object")

    # For failed records with no normalized_data, bootstrap a minimal structure
    base = copy.deepcopy(record.normalized_data) if record.normalized_data else {
        "vinfo": {}, "vnetwork": [], "vpartition": [], "vhost": {}
    }
    base.setdefault("vinfo", {}).update(vinfo_overrides)
    record.normalized_data = base

    # If this was a failed record, promote it to complete on manual save
    if record.processing_status == "error":
        record.processing_status = "complete"
        record.error_message = None
        logger.info(
            "Record %s manually edited — promoted from error → complete", record_id
        )

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


# ---------------------------------------------------------------------------
# Bulk OS replace endpoint
# ---------------------------------------------------------------------------

class BulkOsReplaceBody(BaseModel):
    from_os: str
    to_os: str


class BulkOsReplaceResponse(BaseModel):
    updated_count: int
    from_os: str
    to_os: str


@router.post(
    "/projects/{project_id}/bulk-os-replace",
    response_model=BulkOsReplaceResponse,
)
async def bulk_os_replace(
    project_id: uuid.UUID,
    body: BulkOsReplaceBody,
    db: AsyncSession = Depends(get_db),
) -> BulkOsReplaceResponse:
    """Replace the OS on all non-excluded, normalized records where os_config matches from_os.

    Updates both os_config and os_vmware_tools in normalized_data.vinfo.
    Inserts one Assumption row per updated record documenting the change.
    """
    import copy
    import uuid as _uuid
    from datetime import datetime

    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "complete",
            ServerRecord.is_excluded == False,  # noqa: E712
        )
    )
    records = result.scalars().all()

    updated_count = 0
    for record in records:
        if not record.normalized_data:
            continue
        vinfo = record.normalized_data.get("vinfo", {})
        if vinfo.get("os_config") != body.from_os:
            continue

        # Update the normalized data
        updated = copy.deepcopy(record.normalized_data)
        updated.setdefault("vinfo", {})["os_config"] = body.to_os
        updated["vinfo"]["os_vmware_tools"] = body.to_os
        record.normalized_data = updated

        # Insert assumption documenting the change
        assumption = Assumption(
            id=_uuid.uuid4(),
            server_record_id=record.id,
            project_id=project_id,
            field_name="vinfo/os_config",
            assumed_value=body.to_os,
            original_value=body.from_os,
            reasoning=(
                f"User-initiated bulk OS replacement for pricing purposes: "
                f"'{body.from_os}' → '{body.to_os}'."
            ),
            confidence="medium",
            created_at=datetime.utcnow(),
        )
        db.add(assumption)
        updated_count += 1

    await db.commit()
    logger.info(
        "Bulk OS replace: project %s — '%s' → '%s' (%d records updated)",
        project_id, body.from_os, body.to_os, updated_count,
    )
    return BulkOsReplaceResponse(
        updated_count=updated_count,
        from_os=body.from_os,
        to_os=body.to_os,
    )


# ---------------------------------------------------------------------------
# nxf unsupported-profile count endpoint
# ---------------------------------------------------------------------------

# The three nxf profiles the Cloud Solutioning tool does NOT recognise
# (absent from its Data Domains Compute Family VS column).
_NXF_UNSUPPORTED = {"nxf-1x1", "nxf-1x2", "nxf-1x4"}

# Target profile specs: (num_cpus, memory_mb)
_NXF_TARGETS: dict[str, tuple[int, int]] = {
    "nxf-2x1": (2, 1024),
    "nxf-2x2": (2, 2048),
}


class NxfUnsupportedCountResponse(BaseModel):
    unsupported_count: int


class BulkNxfReplaceBody(BaseModel):
    target_profile: str   # must be "nxf-2x1" or "nxf-2x2"


class BulkNxfReplaceResponse(BaseModel):
    updated_count: int
    target_profile: str


def _nxf_profile_for(cpus: int, mem_mb: int) -> str | None:
    """Return the nxf profile name if (cpus, mem_mb) resolves to one, else None."""
    from services.vpc_calculator_generator import _select_vpc_profile
    mem_gb = max(1, round(mem_mb / 1024))
    _cat, profile, _flag = _select_vpc_profile(cpus, mem_gb)
    return profile if profile in _NXF_UNSUPPORTED else None


@router.get(
    "/projects/{project_id}/nxf-unsupported-count",
    response_model=NxfUnsupportedCountResponse,
)
async def get_nxf_unsupported_count(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> NxfUnsupportedCountResponse:
    """Return the number of active x86 records whose VPC profile would be an
    unsupported nxf-1x* profile (not recognised by the IBM Cloud Solutioning tool)."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "complete",
            ServerRecord.is_excluded == False,  # noqa: E712
        )
    )
    records = result.scalars().all()

    count = 0
    for record in records:
        if not record.normalized_data:
            continue
        if record.server_type == "powervs":
            continue
        vinfo = record.normalized_data.get("vinfo") or {}
        cpus   = int(vinfo.get("num_cpus") or vinfo.get("cpus") or 1)
        mem_mb = int(vinfo.get("memory_mb") or vinfo.get("memory") or 4096)
        if _nxf_profile_for(cpus, mem_mb):
            count += 1

    return NxfUnsupportedCountResponse(unsupported_count=count)


@router.post(
    "/projects/{project_id}/bulk-nxf-replace",
    response_model=BulkNxfReplaceResponse,
)
async def bulk_nxf_replace(
    project_id: uuid.UUID,
    body: BulkNxfReplaceBody,
    db: AsyncSession = Depends(get_db),
) -> BulkNxfReplaceResponse:
    """Replace all unsupported nxf-1x* profiles with a chosen supported target.

    Patches num_cpus and memory_mb in normalized_data.vinfo so the next Cloud
    Solutioning export picks up the new profile.  Inserts one Assumption row per
    updated record documenting the change.
    """
    import copy
    import uuid as _uuid
    from datetime import datetime

    if body.target_profile not in _NXF_TARGETS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"target_profile must be one of {sorted(_NXF_TARGETS)}",
        )

    target_cpus, target_mem_mb = _NXF_TARGETS[body.target_profile]

    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "complete",
            ServerRecord.is_excluded == False,  # noqa: E712
        )
    )
    records = result.scalars().all()

    updated_count = 0
    for record in records:
        if not record.normalized_data:
            continue
        if record.server_type == "powervs":
            continue
        vinfo = record.normalized_data.get("vinfo") or {}
        cpus   = int(vinfo.get("num_cpus") or vinfo.get("cpus") or 1)
        mem_mb = int(vinfo.get("memory_mb") or vinfo.get("memory") or 4096)
        original_profile = _nxf_profile_for(cpus, mem_mb)
        if not original_profile:
            continue

        updated = copy.deepcopy(record.normalized_data)
        updated.setdefault("vinfo", {})["num_cpus"] = target_cpus
        updated["vinfo"]["memory_mb"] = target_mem_mb
        record.normalized_data = updated

        assumption = Assumption(
            id=_uuid.uuid4(),
            server_record_id=record.id,
            project_id=project_id,
            field_name="vinfo/num_cpus+memory_mb",
            assumed_value=body.target_profile,
            original_value=original_profile,
            reasoning=(
                f"User-initiated bulk nxf profile upgrade: '{original_profile}' → "
                f"'{body.target_profile}'. The Cloud Solutioning tool only recognises "
                f"nxf-2x1 and nxf-2x2; nxf-1x* profiles are absent from its Data Domains."
            ),
            confidence="medium",
            created_at=datetime.utcnow(),
        )
        db.add(assumption)
        updated_count += 1

    await db.commit()
    logger.info(
        "Bulk nxf replace: project %s — → '%s' (%d records updated)",
        project_id, body.target_profile, updated_count,
    )
    return BulkNxfReplaceResponse(
        updated_count=updated_count,
        target_profile=body.target_profile,
    )
