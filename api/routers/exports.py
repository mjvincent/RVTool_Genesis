"""Export router — RVTools and Assumptions .xlsx generation and download."""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Assumption, AssumptionsExport, Project, RVToolsExport, ServerRecord
from routers.projects import _get_project_or_404
from services import assumptions_generator, rvtools_generator
from services.rvtools_generator import generate_rvtools_pure_xlsx

logger = logging.getLogger(__name__)

router = APIRouter(tags=["exports"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class RVToolsExportResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    generated_at: datetime
    filename: str
    record_count: int | None
    status: str

    class Config:
        from_attributes = True


class RVToolsExportListResponse(BaseModel):
    exports: list[RVToolsExportResponse]
    total: int


class AssumptionsExportResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    generated_at: datetime
    filename: str
    assumption_count: int | None

    class Config:
        from_attributes = True


class AssumptionsExportListResponse(BaseModel):
    exports: list[AssumptionsExportResponse]
    total: int


# ---------------------------------------------------------------------------
# RVTools export endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/export/rvtools",
    response_model=RVToolsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_rvtools_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RVToolsExportResponse:
    """Generate a new RVTools .xlsx export for the project."""
    project = await _get_project_or_404(db, project_id)

    # Fetch all complete server records with normalized data
    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "complete",
            ServerRecord.normalized_data.is_not(None),
        )
    )
    records = result.scalars().all()

    if not records:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No complete normalized records found for this project. "
                   "Run processing first.",
        )

    normalized_list = [r.normalized_data for r in records if r.normalized_data]

    file_bytes = rvtools_generator.generate_rvtools_xlsx(
        normalized_list, project.name
    )

    safe_name = project.name.replace(" ", "_")
    filename = f"RVTools_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    export = RVToolsExport(
        project_id=project_id,
        file_data=file_bytes,
        filename=filename,
        record_count=len(normalized_list),
        status="complete",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    logger.info(
        "RVTools export %s generated for project %s (%d records)",
        export.id, project_id, len(normalized_list),
    )
    return RVToolsExportResponse.model_validate(export)


@router.get(
    "/projects/{project_id}/exports/rvtools",
    response_model=RVToolsExportListResponse,
)
async def list_rvtools_exports(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RVToolsExportListResponse:
    """List all RVTools exports for a project."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(RVToolsExport)
        .where(RVToolsExport.project_id == project_id)
        .order_by(RVToolsExport.generated_at.desc())
    )
    exports = result.scalars().all()
    return RVToolsExportListResponse(
        exports=[RVToolsExportResponse.model_validate(e) for e in exports],
        total=len(exports),
    )


@router.get(
    "/projects/{project_id}/exports/rvtools/{export_id}/download",
)
async def download_rvtools_export(
    project_id: uuid.UUID,
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream the RVTools .xlsx file as a browser download."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(RVToolsExport).where(
            RVToolsExport.id == export_id,
            RVToolsExport.project_id == project_id,
        )
    )
    export = result.scalar_one_or_none()
    if export is None:
        raise HTTPException(
            status_code=404,
            detail=f"RVTools export {export_id} not found",
        )

    return StreamingResponse(
        io.BytesIO(export.file_data),
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{export.filename}"',
            "Content-Length": str(len(export.file_data)),
        },
    )


# ---------------------------------------------------------------------------
# Pure RVTools export (4-sheet) endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/export/rvtools-pure",
    response_model=RVToolsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_rvtools_pure_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RVToolsExportResponse:
    """Generate a standard 4-sheet RVTools .xlsx (vInfo/vNetwork/vPartition/vHost).

    Use this for tools that consume a plain RVTools export.
    For IBM Cool / VCF Migration Lite use POST /export/rvtools instead.
    """
    project = await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "complete",
            ServerRecord.normalized_data.is_not(None),
        )
    )
    records = result.scalars().all()

    if not records:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No complete normalized records found. Run processing first.",
        )

    normalized_list = [r.normalized_data for r in records if r.normalized_data]
    file_bytes = generate_rvtools_pure_xlsx(normalized_list, project.name)

    safe_name = project.name.replace(" ", "_")
    filename = f"RVToolsPure_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    export = RVToolsExport(
        project_id=project_id,
        file_data=file_bytes,
        filename=filename,
        record_count=len(normalized_list),
        status="complete",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    logger.info(
        "RVTools Pure export %s generated for project %s (%d records)",
        export.id, project_id, len(normalized_list),
    )
    return RVToolsExportResponse.model_validate(export)


# ---------------------------------------------------------------------------
# Assumptions export endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/export/assumptions",
    response_model=AssumptionsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_assumptions_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AssumptionsExportResponse:
    """Generate a new Assumptions Report .xlsx export for the project."""
    project = await _get_project_or_404(db, project_id)

    # Fetch all assumptions for this project, joining server_record for vm_name
    result = await db.execute(
        select(Assumption, ServerRecord.normalized_data)
        .join(
            ServerRecord,
            Assumption.server_record_id == ServerRecord.id,
            isouter=True,
        )
        .where(Assumption.project_id == project_id)
        .order_by(Assumption.created_at)
    )
    rows = result.all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No assumptions found for this project.",
        )

    assumptions_list: list[dict] = []
    for assumption, normalized_data in rows:
        # Extract vm_name from the linked server record's normalized_data
        vm_name: str | None = None
        if normalized_data and isinstance(normalized_data, dict):
            vinfo = normalized_data.get("vinfo") or {}
            vm_name = vinfo.get("vm_name")

        assumptions_list.append({
            "vm_name": vm_name or str(assumption.server_record_id),
            "field_name": assumption.field_name,
            "assumed_value": assumption.assumed_value,
            "original_value": assumption.original_value,
            "reasoning": assumption.reasoning,
            "confidence": assumption.confidence,
            "created_at": assumption.created_at,
        })

    file_bytes = assumptions_generator.generate_assumptions_xlsx(
        assumptions_list, project.name
    )

    safe_name = project.name.replace(" ", "_")
    filename = (
        f"Assumptions_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )

    export = AssumptionsExport(
        project_id=project_id,
        file_data=file_bytes,
        filename=filename,
        assumption_count=len(assumptions_list),
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    logger.info(
        "Assumptions export %s generated for project %s (%d assumptions)",
        export.id, project_id, len(assumptions_list),
    )
    return AssumptionsExportResponse.model_validate(export)


@router.get(
    "/projects/{project_id}/exports/assumptions",
    response_model=AssumptionsExportListResponse,
)
async def list_assumptions_exports(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AssumptionsExportListResponse:
    """List all Assumptions exports for a project."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(AssumptionsExport)
        .where(AssumptionsExport.project_id == project_id)
        .order_by(AssumptionsExport.generated_at.desc())
    )
    exports = result.scalars().all()
    return AssumptionsExportListResponse(
        exports=[AssumptionsExportResponse.model_validate(e) for e in exports],
        total=len(exports),
    )


@router.get(
    "/projects/{project_id}/exports/assumptions/{export_id}/download",
)
async def download_assumptions_export(
    project_id: uuid.UUID,
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream the Assumptions Report .xlsx as a browser download."""
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(AssumptionsExport).where(
            AssumptionsExport.id == export_id,
            AssumptionsExport.project_id == project_id,
        )
    )
    export = result.scalar_one_or_none()
    if export is None:
        raise HTTPException(
            status_code=404,
            detail=f"Assumptions export {export_id} not found",
        )

    return StreamingResponse(
        io.BytesIO(export.file_data),
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{export.filename}"',
            "Content-Length": str(len(export.file_data)),
        },
    )
