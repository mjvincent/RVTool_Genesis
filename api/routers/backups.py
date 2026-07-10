"""Backup and restore endpoints for RVTool Genesis projects.

Backup format (schema_version=1):
  {
    "schema_version": 1,
    "exported_at": "ISO-8601",
    "project": { id, name, description, created_at, updated_at },
    "records": [
      {
        "id", "upload_id", "raw_data", "normalized_data",
        "server_type", "processing_status", "is_excluded", "exclusion_reason",
        "error_message", "created_at", "updated_at",
        "assumptions": [ { field_name, assumed_value, original_value,
                           reasoning, confidence, created_at } ]
      }
    ],
    "original_file": {            # only when include_file=True
      "filename": str,
      "row_count": int,
      "data_base64": str
    }
  }

Multi-project (full system) backup: a .zip containing one .json per project.
"""
import base64
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.database import get_db
from db.models import Assumption, Project, ServerRecord, Upload

router = APIRouter()

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


async def _serialize_project(
    project_id: uuid.UUID,
    db: AsyncSession,
    include_file: bool,
) -> dict:
    """Build the full JSON bundle for a single project."""
    # Load project
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Load server records with assumptions eager-loaded
    rec_result = await db.execute(
        select(ServerRecord)
        .where(ServerRecord.project_id == project_id)
        .options(selectinload(ServerRecord.assumptions))
        .order_by(ServerRecord.created_at)
    )
    records = rec_result.scalars().all()

    # Load the most-recent upload for this project (for original file bytes)
    upload_result = await db.execute(
        select(Upload)
        .where(Upload.project_id == project_id)
        .order_by(Upload.uploaded_at.desc())
        .limit(1)
    )
    upload = upload_result.scalar_one_or_none()

    # Serialise records
    records_out = []
    for rec in records:
        assumptions_out = []
        for a in rec.assumptions:
            assumptions_out.append({
                "field_name": a.field_name,
                "assumed_value": a.assumed_value,
                "original_value": a.original_value,
                "reasoning": a.reasoning,
                "confidence": a.confidence,
                "created_at": _dt_str(a.created_at),
            })
        records_out.append({
            "id": str(rec.id),
            "upload_id": str(rec.upload_id),
            "raw_data": rec.raw_data,
            "normalized_data": rec.normalized_data,
            "server_type": rec.server_type,
            "processing_status": rec.processing_status,
            "is_excluded": rec.is_excluded,
            "exclusion_reason": rec.exclusion_reason,
            "error_message": rec.error_message,
            "created_at": _dt_str(rec.created_at),
            "updated_at": _dt_str(rec.updated_at),
            "assumptions": assumptions_out,
        })

    bundle: dict = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "created_at": _dt_str(project.created_at),
            "updated_at": _dt_str(project.updated_at),
        },
        "records": records_out,
    }

    if include_file and upload is not None:
        bundle["original_file"] = {
            "filename": upload.filename,
            "row_count": upload.row_count,
            "data_base64": base64.b64encode(upload.raw_file).decode("utf-8"),
        }

    return bundle


async def _restore_project_from_dict(bundle: dict, db: AsyncSession) -> Project:
    """Restore a single project from a JSON bundle dict. Always creates new project."""
    if bundle.get("schema_version") != SCHEMA_VERSION:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported backup schema_version: {bundle.get('schema_version')}. Expected {SCHEMA_VERSION}.",
        )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    proj_data = bundle["project"]

    new_project = Project(
        id=uuid.uuid4(),
        name=f"{proj_data['name']} (restored {today})",
        description=proj_data.get("description"),
    )
    db.add(new_project)
    await db.flush()  # get new_project.id

    # Create upload row
    orig_file = bundle.get("original_file")
    if orig_file:
        raw_bytes = base64.b64decode(orig_file["data_base64"])
        upload = Upload(
            id=uuid.uuid4(),
            project_id=new_project.id,
            filename=orig_file["filename"],
            raw_file=raw_bytes,
            row_count=orig_file.get("row_count"),
            status="complete",
        )
    else:
        upload = Upload(
            id=uuid.uuid4(),
            project_id=new_project.id,
            filename="(restored — original file not included)",
            raw_file=b"",
            status="complete",
        )
    db.add(upload)
    await db.flush()

    # Restore server records and assumptions
    for rec_data in bundle.get("records", []):
        new_rec = ServerRecord(
            id=uuid.uuid4(),
            upload_id=upload.id,
            project_id=new_project.id,
            raw_data=rec_data.get("raw_data") or {},
            normalized_data=rec_data.get("normalized_data"),
            server_type=rec_data.get("server_type"),
            processing_status=rec_data.get("processing_status", "complete"),
            is_excluded=rec_data.get("is_excluded", False),
            exclusion_reason=rec_data.get("exclusion_reason"),
            error_message=rec_data.get("error_message"),
        )
        db.add(new_rec)
        await db.flush()

        for a_data in rec_data.get("assumptions", []):
            assumption = Assumption(
                id=uuid.uuid4(),
                server_record_id=new_rec.id,
                project_id=new_project.id,
                field_name=a_data.get("field_name", ""),
                assumed_value=a_data.get("assumed_value", ""),
                original_value=a_data.get("original_value"),
                reasoning=a_data.get("reasoning", ""),
                confidence=a_data.get("confidence", "medium"),
            )
            db.add(assumption)

    await db.commit()
    await db.refresh(new_project)
    return new_project


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/backup")
async def backup_project(
    project_id: uuid.UUID,
    include_file: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Download a single project as a JSON backup bundle."""
    bundle = await _serialize_project(project_id, db, include_file)
    slug = bundle["project"]["name"].lower().replace(" ", "-")[:40]
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"rvtg-{slug}-{date_str}.json"

    json_bytes = json.dumps(bundle, indent=2, default=str).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/backup/all")
async def backup_all_projects(
    include_files: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Download all projects as a .zip archive of JSON bundles."""
    result = await db.execute(select(Project).order_by(Project.created_at))
    projects = result.scalars().all()

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for project in projects:
            bundle = await _serialize_project(project.id, db, include_files)
            slug = bundle["project"]["name"].lower().replace(" ", "-")[:40]
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
            entry_name = f"rvtg-{slug}-{date_str}.json"
            zf.writestr(entry_name, json.dumps(bundle, indent=2, default=str))

    zip_buffer.seek(0)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"rvtoolgenesis-backup-{date_str}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_projects(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Restore one or more projects from a .json or .zip backup file."""
    content = await file.read()
    filename = file.filename or ""

    restored = []

    if filename.endswith(".zip"):
        # Multi-project zip
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                for entry in zf.namelist():
                    if not entry.endswith(".json"):
                        continue
                    bundle = json.loads(zf.read(entry))
                    project = await _restore_project_from_dict(bundle, db)
                    restored.append({"id": str(project.id), "name": project.name})
        except zipfile.BadZipFile:
            raise HTTPException(status_code=422, detail="Invalid zip file.")
    elif filename.endswith(".json"):
        try:
            bundle = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid JSON: {exc}")
        project = await _restore_project_from_dict(bundle, db)
        restored.append({"id": str(project.id), "name": project.name})
    else:
        raise HTTPException(
            status_code=422,
            detail="Unsupported file type. Upload a .json or .zip backup file.",
        )

    return JSONResponse({"restored": restored, "count": len(restored)})
