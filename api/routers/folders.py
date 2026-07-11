"""Folders router — /api/folders

Folders provide a 2-level hierarchy for organising projects:
  Root level:  customer folders  (parent_id = NULL)
  Child level: engagement folders (parent_id = <customer folder id>)

The 2-level cap is enforced at creation time: a child folder cannot
itself become a parent.
"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Folder, Project
from schemas.folder import FolderCreate, FolderListResponse, FolderRename, FolderResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["folders"])


# ---------------------------------------------------------------------------
# List folders (optionally filtered by parent)
# ---------------------------------------------------------------------------

@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    parent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> FolderListResponse:
    """Return folders at the given level.

    - parent_id omitted / null  → root-level folders
    - parent_id=<uuid>          → children of that folder
    """
    if parent_id is None:
        stmt = select(Folder).where(Folder.parent_id.is_(None)).order_by(Folder.name)
    else:
        try:
            pid = uuid.UUID(parent_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid parent_id UUID")
        stmt = select(Folder).where(Folder.parent_id == pid).order_by(Folder.name)

    result = await db.execute(stmt)
    folders = result.scalars().all()

    responses = []
    for f in folders:
        pc = await db.scalar(select(func.count()).where(Project.folder_id == f.id)) or 0
        cc = await db.scalar(select(func.count()).where(Folder.parent_id == f.id)) or 0
        r = FolderResponse.model_validate(f)
        r.project_count = pc
        r.child_count = cc
        responses.append(r)

    return FolderListResponse(folders=responses, total=len(responses))


# ---------------------------------------------------------------------------
# Create folder
# ---------------------------------------------------------------------------

@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderCreate,
    db: AsyncSession = Depends(get_db),
) -> FolderResponse:
    # Enforce max depth = 2
    if body.parent_id is not None:
        parent = await _get_folder_or_404(db, body.parent_id)
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=400,
                detail="Maximum folder depth is 2 (customer → engagement). "
                       "Cannot create a sub-folder inside an engagement folder.",
            )

    folder = Folder(name=body.name.strip(), parent_id=body.parent_id)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    r = FolderResponse.model_validate(folder)
    r.project_count = 0
    r.child_count = 0
    return r


# ---------------------------------------------------------------------------
# Get single folder
# ---------------------------------------------------------------------------

@router.get("/folders/{folder_id}", response_model=FolderResponse)
async def get_folder(
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FolderResponse:
    folder = await _get_folder_or_404(db, folder_id)
    pc = await db.scalar(select(func.count()).where(Project.folder_id == folder.id)) or 0
    cc = await db.scalar(select(func.count()).where(Folder.parent_id == folder.id)) or 0
    r = FolderResponse.model_validate(folder)
    r.project_count = pc
    r.child_count = cc
    return r


# ---------------------------------------------------------------------------
# Rename folder
# ---------------------------------------------------------------------------

@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def rename_folder(
    folder_id: uuid.UUID,
    body: FolderRename,
    db: AsyncSession = Depends(get_db),
) -> FolderResponse:
    folder = await _get_folder_or_404(db, folder_id)
    folder.name = body.name.strip()
    await db.commit()
    await db.refresh(folder)
    pc = await db.scalar(select(func.count()).where(Project.folder_id == folder.id)) or 0
    cc = await db.scalar(select(func.count()).where(Folder.parent_id == folder.id)) or 0
    r = FolderResponse.model_validate(folder)
    r.project_count = pc
    r.child_count = cc
    return r


# ---------------------------------------------------------------------------
# Delete folder
# ---------------------------------------------------------------------------

@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a folder. Projects inside are moved to root (folder_id → NULL).
    Child folders are cascade-deleted by the DB FK.
    """
    folder = await _get_folder_or_404(db, folder_id)

    # Detach direct projects → root before deleting folder
    result = await db.execute(select(Project).where(Project.folder_id == folder_id))
    for project in result.scalars().all():
        project.folder_id = None

    await db.delete(folder)
    await db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_folder_or_404(db: AsyncSession, folder_id: uuid.UUID) -> Folder:
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
    return folder
