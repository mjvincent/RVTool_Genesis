"""Project CRUD router — /api/projects"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Project, Upload
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project
