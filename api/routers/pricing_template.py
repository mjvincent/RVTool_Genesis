"""Pricing template router — upload IBM Price Estimator and populate it with PowerVS data."""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import PricingTemplate, Project, ServerRecord
from routers.projects import _get_project_or_404
from schemas.pricing_template import PricingTemplateResponse, PricingTemplateStatus
from services import pricing_template_filler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pricing-template"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

_EXPECTED_SHEET = "Multiple LPAR Price Estimate"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_powervs_records(project_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Return enriched dicts for non-excluded PowerVS records with complete processing."""
    result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_id,
            ServerRecord.processing_status == "complete",
            ServerRecord.normalized_data.is_not(None),
            ServerRecord.server_type == "powervs",
            ServerRecord.is_excluded.is_(False),
        )
    )
    records = result.scalars().all()
    return [
        {
            "normalized_data": r.normalized_data,
            "server_type": r.server_type or "powervs",
            "is_excluded": r.is_excluded,
        }
        for r in records
        if r.normalized_data
    ]


# ---------------------------------------------------------------------------
# GET /projects/{id}/pricing-template/status
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/pricing-template/status",
    response_model=PricingTemplateStatus,
)
async def get_pricing_template_status(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PricingTemplateStatus:
    """Return whether a pricing template has been uploaded for this project."""
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(PricingTemplate).where(PricingTemplate.project_id == project_id)
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        return PricingTemplateStatus(has_template=False, filename=None, updated_at=None)
    return PricingTemplateStatus(
        has_template=True,
        filename=tmpl.filename,
        updated_at=tmpl.updated_at,
    )


# ---------------------------------------------------------------------------
# POST /projects/{id}/pricing-template  (upload / replace)
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/pricing-template",
    response_model=PricingTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_pricing_template(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> PricingTemplateResponse:
    """Upload (or replace) the IBM Price Estimator template for this project.

    Validates that the file contains the expected sheet name.
    Stores the raw bytes in the DB — one record per project (upsert).
    """
    await _get_project_or_404(db, project_id)

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File must be a .xlsx workbook.",
        )

    file_bytes = await file.read()

    # Quick structural validation — check for expected sheet
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False, keep_vba=False)
        if _EXPECTED_SHEET not in wb.sheetnames:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Workbook does not contain the sheet '{_EXPECTED_SHEET}'. "
                    "Please upload a valid IBM Power Virtual Server Price Estimator workbook."
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not read workbook: {exc}",
        ) from exc

    # Upsert — replace existing template for this project
    result = await db.execute(
        select(PricingTemplate).where(PricingTemplate.project_id == project_id)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        existing.filename  = file.filename
        existing.file_data = file_bytes
        existing.updated_at = datetime.utcnow()
        tmpl = existing
    else:
        tmpl = PricingTemplate(
            project_id=project_id,
            filename=file.filename,
            file_data=file_bytes,
        )
        db.add(tmpl)

    await db.commit()
    await db.refresh(tmpl)

    logger.info(
        "Pricing template '%s' uploaded for project %s (%d bytes)",
        file.filename, project_id, len(file_bytes),
    )
    return PricingTemplateResponse.model_validate(tmpl)


# ---------------------------------------------------------------------------
# POST /projects/{id}/export/pricing-estimator  (populate + download)
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/export/pricing-estimator",
    status_code=status.HTTP_200_OK,
)
async def generate_pricing_estimator_export(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Populate the uploaded IBM Price Estimator with PowerVS server data.

    Opens the stored template, writes the yellow input cells only (LPAR name,
    data center, system, processor type, cores, memory, OS, storage), and
    returns the populated workbook as a streaming download.  All formulas and
    other sheets are preserved intact — open the file in Excel to see pricing.
    """
    project = await _get_project_or_404(db, project_id)

    # Fetch template
    result = await db.execute(
        select(PricingTemplate).where(PricingTemplate.project_id == project_id)
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No pricing template uploaded for this project. "
                   "Upload the IBM Price Estimator workbook first.",
        )

    # Fetch PowerVS records
    powervs_records = await _fetch_powervs_records(project_id, db)
    if not powervs_records:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No PowerVS records found for this project.",
        )

    pvs_datacenter = project.pvs_datacenter or "dal10"

    try:
        filled_bytes, written, skipped, machine_counts = pricing_template_filler.fill_pricing_template(
            tmpl.file_data,
            powervs_records,
            pvs_datacenter=pvs_datacenter,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    safe_name = project.name.replace(" ", "_")
    filename  = f"PowerVS_PriceEstimator_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    logger.info(
        "Pricing estimator export for project %s: %d servers written, %d skipped (>%d limit), dc=%s, machines=%s",
        project_id, written, skipped, pricing_template_filler._ROWS_PER_SHEET, pvs_datacenter, machine_counts,
    )

    if skipped > 0:
        logger.warning(
            "Project %s has %d PowerVS servers exceeding the %d-row sheet limit — "
            "%d servers were not written to the template.",
            project_id, len(powervs_records),
            pricing_template_filler._ROWS_PER_SHEET, skipped,
        )

    # Expose summary counts as custom headers so the frontend can render a breakdown card.
    # X-Written-Count:  total LPARs written
    # X-Skipped-Count:  LPARs omitted (over sheet limit)
    # X-Machine-Counts: JSON object e.g. {"S1022":12,"E1050":4}
    import json as _json
    extra_headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Written-Count": str(written),
        "X-Skipped-Count": str(skipped),
        "X-Machine-Counts": _json.dumps(machine_counts),
        "Access-Control-Expose-Headers": "X-Written-Count, X-Skipped-Count, X-Machine-Counts",
    }

    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type=_XLSX_MEDIA_TYPE,
        headers=extra_headers,
    )
