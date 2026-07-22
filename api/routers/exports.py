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
from services import assumptions_generator, powervs_calculator_generator, rvtools_generator, vpc_calculator_generator
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
# Helpers — shared by all export endpoints
# ---------------------------------------------------------------------------

async def _fetch_enriched_records(project_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Fetch complete ServerRecords and return enriched dicts for the generator.

    Returns list of {"normalized_data": ..., "server_type": ..., "is_excluded": bool}.
    """
    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "complete",
            ServerRecord.normalized_data.is_not(None),
        )
    )
    records = result.scalars().all()
    return [
        {
            "normalized_data": r.normalized_data,
            "server_type": r.server_type or "vm",
            "is_excluded": r.is_excluded,
            "exclusion_reason": r.exclusion_reason,
            "updated_at": r.updated_at,
        }
        for r in records
        if r.normalized_data
    ]


async def _fetch_excluded_servers(project_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Fetch excluded server records for the Excluded Servers audit sheet."""
    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.is_excluded.is_(True),
        )
    )
    excluded = result.scalars().all()
    out = []
    for r in excluded:
        nd = r.normalized_data or {}
        vinfo = nd.get("vinfo") or {}
        out.append({
            "vm_name": vinfo.get("vm_name") or str(r.id),
            "os_config": vinfo.get("os_config"),
            "server_type": r.server_type,
            "exclusion_reason": r.exclusion_reason,
            "excluded_at": r.updated_at,
        })
    return out


# ---------------------------------------------------------------------------
# RVTools export endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/powervs-count",
)
async def get_powervs_count(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return count of PowerVS records in this project (for Export page conditional rendering)."""
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "complete",
            ServerRecord.server_type == "powervs",
            ServerRecord.is_excluded.is_(False),
        )
    )
    count = len(result.scalars().all())
    return {"powervs_count": count}


@router.post(
    "/projects/{project_id}/export/rvtools",
    response_model=RVToolsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_rvtools_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RVToolsExportResponse:
    """Generate x86/VPC RVTools .xlsx (excludes PowerVS and excluded servers)."""
    project = await _get_project_or_404(db, project_id)
    enriched = await _fetch_enriched_records(project_id, db)

    if not enriched:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No complete normalized records found for this project. "
                   "Run processing first.",
        )

    file_bytes = rvtools_generator.generate_rvtools_xlsx(
        enriched, project.name, x86_only=True
    )
    active_count = sum(
        1 for r in enriched
        if not r["is_excluded"] and r["server_type"] != "powervs"
    )

    safe_name = project.name.replace(" ", "_")
    filename = f"RVTools_x86_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    export = RVToolsExport(
        project_id=project_id,
        file_data=file_bytes,
        filename=filename,
        record_count=active_count,
        status="complete",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    logger.info(
        "RVTools x86 export %s generated for project %s (%d records)",
        export.id, project_id, active_count,
    )
    return RVToolsExportResponse.model_validate(export)


@router.post(
    "/projects/{project_id}/export/rvtools-powervs",
    response_model=RVToolsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_rvtools_powervs_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RVToolsExportResponse:
    """Generate PowerVS-only Cool Tool .xlsx (4-sheet, AIX/IBM i records only).

    Uses the 4-sheet format because IBM Cool reads the 4-sheet RVTools format as input.
    """
    project = await _get_project_or_404(db, project_id)
    enriched = await _fetch_enriched_records(project_id, db)

    powervs_records = [r for r in enriched if r["server_type"] == "powervs" and not r["is_excluded"]]
    if not powervs_records:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No PowerVS (AIX/IBM i) records found in this project.",
        )

    # 4-sheet format — the format IBM Cool reads as input
    pvs_normalized = [r["normalized_data"] for r in powervs_records if r["normalized_data"]]
    file_bytes = generate_rvtools_pure_xlsx(pvs_normalized, project.name)

    safe_name = project.name.replace(" ", "_")
    filename = f"RVTools_PowerVS_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    export = RVToolsExport(
        project_id=project_id,
        file_data=file_bytes,
        filename=filename,
        record_count=len(powervs_records),
        status="complete",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    logger.info(
        "RVTools PowerVS export %s generated for project %s (%d records)",
        export.id, project_id, len(powervs_records),
    )
    return RVToolsExportResponse.model_validate(export)


@router.post(
    "/projects/{project_id}/export/rvtools-powervs-full",
    response_model=RVToolsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_rvtools_powervs_full_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RVToolsExportResponse:
    """Generate PowerVS-only RVTools .xlsx in full 22-sheet format.

    Uses the 22-sheet format for tools like VCF Migration Lite that validate
    all 22 RVTools tabs on import. PowerVS (AIX/IBM i) records only.
    """
    project = await _get_project_or_404(db, project_id)
    enriched = await _fetch_enriched_records(project_id, db)

    powervs_records = [r for r in enriched if r["server_type"] == "powervs" and not r["is_excluded"]]
    if not powervs_records:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No PowerVS (AIX/IBM i) records found in this project.",
        )

    file_bytes = rvtools_generator.generate_rvtools_xlsx(
        enriched, project.name, powervs_only=True
    )

    safe_name = project.name.replace(" ", "_")
    filename = f"RVTools_PowerVS_Full_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    export = RVToolsExport(
        project_id=project_id,
        file_data=file_bytes,
        filename=filename,
        record_count=len(powervs_records),
        status="complete",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    logger.info(
        "RVTools PowerVS full (22-sheet) export %s generated for project %s (%d records)",
        export.id, project_id, len(powervs_records),
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
# IBM Cloud VPC Calculator export (3-sheet) endpoint
# ---------------------------------------------------------------------------

class VPCCalculatorRequest(BaseModel):
    billing_type: str = "PAYG"


@router.post(
    "/projects/{project_id}/export/vpc-calculator",
    response_model=RVToolsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_vpc_calculator_export(
    project_id: uuid.UUID,
    body: VPCCalculatorRequest = VPCCalculatorRequest(),
    db: AsyncSession = Depends(get_db),
) -> RVToolsExportResponse:
    """Generate a 3-sheet IBM Cloud VPC Calculator workbook.

    Mirrors the output of the rvtools2vpc.vmware-solutions.cloud.ibm.com tool:
      - Project Settings (Zone + Subnet + Compute + Data Volume rows per VM)
      - Exceptions       (VMs with no matching IBM VPC profile)
      - Data Domains     (static IBM reference lookup table)

    Target region and datacenter are read from the project's vpc_region /
    vpc_datacenter fields (set at project creation, editable in New Project form).
    Billing type is supplied per-export: PAYG, 1 Yr Reserved, or 3 Yr Reserved.
    """
    project = await _get_project_or_404(db, project_id)
    enriched = await _fetch_enriched_records(project_id, db)

    x86_records = [
        r for r in enriched
        if not r["is_excluded"] and r["server_type"] != "powervs"
    ]
    if not x86_records:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No complete x86 records found for this project. "
                   "Run processing first.",
        )

    vpc_region     = project.vpc_region or "us-south"
    vpc_datacenter = project.vpc_datacenter or "us-south-1"

    file_bytes = vpc_calculator_generator.generate_vpc_calculator_xlsx(
        x86_records,
        project.name,
        vpc_region=vpc_region,
        vpc_datacenter=vpc_datacenter,
        billing_type=body.billing_type,
    )

    safe_name = project.name.replace(" ", "_")
    filename = f"CloudSolution_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    export = RVToolsExport(
        project_id=project_id,
        file_data=file_bytes,
        filename=filename,
        record_count=len(x86_records),
        status="complete",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    logger.info(
        "VPC Calculator export %s generated for project %s (%d records, region=%s, dc=%s, billing=%s)",
        export.id, project_id, len(x86_records), vpc_region, vpc_datacenter, body.billing_type,
    )
    return RVToolsExportResponse.model_validate(export)


@router.post(
    "/projects/{project_id}/export/powervs-calculator",
    response_model=RVToolsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_powervs_calculator_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RVToolsExportResponse:
    """Generate a 3-sheet IBM PowerVS Calculator workbook.

    Produces the PowerVS equivalent of the VPC Cloud Solution Export:
      - Project Settings (Zone + per-server Compute rows)
      - Exceptions       (servers exceeding known machine type limits)
      - Data Domains     (static PowerVS reference lookup table)

    Target region and datacenter are read from the project's pvs_region /
    pvs_datacenter fields (PowerVS uses short names like dal10, lon06).
    """
    project = await _get_project_or_404(db, project_id)
    enriched = await _fetch_enriched_records(project_id, db)

    powervs_records = [
        r for r in enriched
        if r["server_type"] == "powervs" and not r["is_excluded"]
    ]
    if not powervs_records:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No PowerVS (AIX/IBM i) records found in this project.",
        )

    pvs_region     = project.pvs_region or "us-south"
    pvs_datacenter = project.pvs_datacenter or "dal10"

    file_bytes = powervs_calculator_generator.generate_powervs_calculator_xlsx(
        enriched,
        project.name,
        pvs_region=pvs_region,
        pvs_datacenter=pvs_datacenter,
    )

    safe_name = project.name.replace(" ", "_")
    filename = f"CloudSolution_PowerVS_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    export = RVToolsExport(
        project_id=project_id,
        file_data=file_bytes,
        filename=filename,
        record_count=len(powervs_records),
        status="complete",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    logger.info(
        "PowerVS Calculator export %s generated for project %s (%d records, region=%s, dc=%s)",
        export.id, project_id, len(powervs_records), pvs_region, pvs_datacenter,
    )
    return RVToolsExportResponse.model_validate(export)


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
    """Generate x86-only 4-sheet RVTools .xlsx (excludes PowerVS and excluded servers)."""
    project = await _get_project_or_404(db, project_id)
    enriched = await _fetch_enriched_records(project_id, db)

    if not enriched:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No complete normalized records found. Run processing first.",
        )

    # Extract x86-only normalized_data for the pure generator
    x86_normalized = [
        r["normalized_data"] for r in enriched
        if not r["is_excluded"] and r["server_type"] != "powervs"
    ]
    file_bytes = generate_rvtools_pure_xlsx(x86_normalized, project.name)
    safe_name = project.name.replace(" ", "_")
    filename = f"RVTools_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    export = RVToolsExport(
        project_id=project_id,
        file_data=file_bytes,
        filename=filename,
        record_count=len(x86_normalized),
        status="complete",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    logger.info(
        "RVTools Pure x86 export %s generated for project %s (%d records)",
        export.id, project_id, len(x86_normalized),
    )
    return RVToolsExportResponse.model_validate(export)


# ---------------------------------------------------------------------------
# Assumptions export endpoints
# ---------------------------------------------------------------------------

async def _build_assumptions_list(
    project_id: uuid.UUID,
    db: AsyncSession,
    powervs_only: bool = False,
) -> list[dict]:
    """Shared helper: build assumptions list, optionally filtered to PowerVS records."""
    result = await db.execute(
        select(Assumption, ServerRecord.normalized_data, ServerRecord.server_type)
        .join(ServerRecord, Assumption.server_record_id == ServerRecord.id, isouter=True)
        .where(Assumption.project_id == project_id)
        .order_by(Assumption.created_at)
    )
    rows = result.all()
    assumptions_list: list[dict] = []
    for assumption, normalized_data, server_type in rows:
        if powervs_only and server_type != "powervs":
            continue
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
    return assumptions_list


@router.post(
    "/projects/{project_id}/export/assumptions",
    response_model=AssumptionsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_assumptions_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AssumptionsExportResponse:
    """Generate Assumptions Report with all x86 records + Excluded Servers sheet."""
    project = await _get_project_or_404(db, project_id)
    assumptions_list = await _build_assumptions_list(project_id, db, powervs_only=False)

    if not assumptions_list:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No assumptions found for this project.",
        )

    excluded_servers = await _fetch_excluded_servers(project_id, db)
    file_bytes = assumptions_generator.generate_assumptions_xlsx(
        assumptions_list, project.name, excluded_servers=excluded_servers
    )

    safe_name = project.name.replace(" ", "_")
    filename = f"Assumptions_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

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


@router.post(
    "/projects/{project_id}/export/assumptions-powervs",
    response_model=AssumptionsExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_assumptions_powervs_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AssumptionsExportResponse:
    """Generate PowerVS-only Assumptions Report."""
    project = await _get_project_or_404(db, project_id)
    assumptions_list = await _build_assumptions_list(project_id, db, powervs_only=True)

    if not assumptions_list:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No PowerVS assumptions found for this project.",
        )

    file_bytes = assumptions_generator.generate_assumptions_xlsx(
        assumptions_list, project.name, powervs_only=True
    )

    safe_name = project.name.replace(" ", "_")
    filename = f"Assumptions_PowerVS_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

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
        "PowerVS Assumptions export %s generated for project %s (%d assumptions)",
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
