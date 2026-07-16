"""Project CRUD router — /api/projects"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import PricingTemplate, Project, Upload
from schemas.project import ProjectCreate, ProjectListResponse, ProjectResponse, ProjectUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = Project(
        name=body.name,
        description=body.description,
        folder_id=body.folder_id,
        vpc_region=body.vpc_region or "us-south",
        vpc_datacenter=body.vpc_datacenter or "us-south-1",
        pvs_region=body.pvs_region or "us-south",
        pvs_datacenter=body.pvs_datacenter or "dal10",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    folder_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ProjectListResponse:
    """List projects, optionally filtered by folder.

    - folder_id omitted        → all projects (used by backup/restore flows)
    - folder_id=null           → root-level projects (no folder assigned)
    - folder_id=<uuid>         → projects inside that folder
    """
    stmt = select(Project)
    if folder_id == "null":
        stmt = stmt.where(Project.folder_id.is_(None))
    elif folder_id is not None:
        try:
            fid = uuid.UUID(folder_id)
            stmt = stmt.where(Project.folder_id == fid)
        except ValueError:
            pass  # ignore invalid UUID, return all
    result = await db.execute(stmt.order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return ProjectListResponse(
        projects=[ProjectResponse.model_validate(p) for p in projects],
        total=len(projects),
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = await _get_project_or_404(db, project_id)
    return ProjectResponse.model_validate(project)


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = await _get_project_or_404(db, project_id)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.folder_id is not None:
        project.folder_id = body.folder_id
    if body.vpc_region is not None:
        project.vpc_region = body.vpc_region
    if body.vpc_datacenter is not None:
        project.vpc_datacenter = body.vpc_datacenter
    if body.pvs_region is not None:
        project.pvs_region = body.pvs_region
    if body.pvs_datacenter is not None:
        project.pvs_datacenter = body.pvs_datacenter
    await db.commit()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    project = await _get_project_or_404(db, project_id)
    await db.delete(project)
    await db.commit()


@router.post("/projects/{project_id}/duplicate", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_project(
    project_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Shallow-copy a project: metadata, region settings, and the stored pricing template.

    No uploads or server records are copied — the user can re-upload if needed.
    The new project name is taken from the request body (field: ``name``).
    """
    from pydantic import BaseModel

    source = await _get_project_or_404(db, project_id)
    new_name: str = (body.get("name") or f"{source.name} (copy)").strip()

    new_project = Project(
        name=new_name,
        description=source.description,
        folder_id=source.folder_id,
        vpc_region=source.vpc_region,
        vpc_datacenter=source.vpc_datacenter,
        pvs_region=source.pvs_region,
        pvs_datacenter=source.pvs_datacenter,
    )
    db.add(new_project)
    await db.flush()  # populate new_project.id before copying the template

    # Copy the stored IBM Price Estimator template if one exists
    tmpl_result = await db.execute(
        select(PricingTemplate).where(PricingTemplate.project_id == project_id)
    )
    source_tmpl = tmpl_result.scalar_one_or_none()
    if source_tmpl is not None:
        new_tmpl = PricingTemplate(
            project_id=new_project.id,
            filename=source_tmpl.filename,
            file_data=source_tmpl.file_data,
        )
        db.add(new_tmpl)

    await db.commit()
    await db.refresh(new_project)
    logger.info("Duplicated project %s → %s (name=%r)", project_id, new_project.id, new_name)
    return ProjectResponse.model_validate(new_project)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project
