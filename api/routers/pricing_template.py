"""PowerVS Price Estimator template filler router.

POST /api/pricing-template/fill
  Accepts a multipart form with:
    - template: UploadFile  (.xlsx — the blank IBM PowerVS Price Estimator)
    - job_id:   str         (project UUID — used to look up PowerVS server records)
    - datacenter: str       (optional override, default 'DAL10')
  Returns: filled .xlsx as a streaming download.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Project, ServerRecord
from services.pricing_template_filler import fill_powervs_price_estimator

router = APIRouter(tags=["pricing-template"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.post("/fill")
async def fill_price_estimator(
    template: UploadFile,
    job_id: str = Form(...),
    datacenter: str = Form("DAL10"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Fill a PowerVS Price Estimator template with LPAR data from a project.

    The template is the blank IBM PowerVS Price Estimator .xlsx file the user
    uploads fresh each time.  It is never cached — each call receives a new upload.
    """
    # Validate project exists
    try:
        project_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job_id (must be a UUID)")

    result = await db.execute(select(Project).where(Project.id == project_uuid))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {job_id} not found")

    # Fetch PowerVS server records for this project
    rec_result = await db.execute(
        select(ServerRecord).where(
            ServerRecord.project_id == project_uuid,
            ServerRecord.processing_status == "complete",
            ServerRecord.is_excluded.is_(False),
            ServerRecord.server_type == "powervs",
            ServerRecord.normalized_data.is_not(None),
        )
    )
    db_records = rec_result.scalars().all()

    if not db_records:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No completed PowerVS records found for this project. Process the upload first.",
        )

    # Build flat server dicts for the filler service
    servers: list[dict] = []
    for r in db_records:
        nd = r.normalized_data or {}
        vinfo = nd.get("vinfo") or {}

        # Resolve cores — entitled processors stored as float (e.g. 4.5)
        cpus_raw = (
            vinfo.get("cpus")
            or vinfo.get("num_cpus")
            or vinfo.get("cpu_count")
            or 0
        )
        try:
            cores = float(cpus_raw)
        except (TypeError, ValueError):
            cores = 0.0

        mem_mb_raw = vinfo.get("memory_mb") or vinfo.get("memory") or 0
        try:
            mem_mb = float(mem_mb_raw)
        except (TypeError, ValueError):
            mem_mb = 0.0
        memory_gb = max(1.0, round(mem_mb / 1024, 0)) if mem_mb > 0 else 4.0

        disk_mb_raw = (
            vinfo.get("total_disk_mb")
            or vinfo.get("provisioned_mb")
            or 0
        )
        try:
            disk_mb = float(disk_mb_raw)
        except (TypeError, ValueError):
            disk_mb = 0.0
        storage_gb = max(1, round(disk_mb / 1024)) if disk_mb > 0 else 100

        servers.append({
            "server_name":    vinfo.get("vm_name") or str(r.id),
            "machine_type":   vinfo.get("machine_type") or "S1022",
            "processor_type": vinfo.get("processor_type") or "S",
            "cores":          cores,
            "memory_gb":      memory_gb,
            "os_config":      vinfo.get("os_config") or vinfo.get("os_family"),
            "storage_gb":     storage_gb,
        })

    # Read template bytes (no caching — always fresh)
    template_bytes = await template.read()
    if not template_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded template file is empty")

    # Fill the template
    try:
        filled_bytes = fill_powervs_price_estimator(
            template_bytes=template_bytes,
            servers=servers,
            datacenter=datacenter.upper(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fill template: {exc}",
        )

    # Build filename
    project_slug = (project.name or "PowerVS").replace(" ", "_")[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"PowerVS_PriceEstimator_{project_slug}_{ts}.xlsx"

    import io
    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
