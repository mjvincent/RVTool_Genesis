"""Pydantic v2 schemas for Folder CRUD."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class FolderCreate(BaseModel):
    name: str
    parent_id: UUID | None = None

    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Folder name cannot be empty")
        return v


class FolderRename(BaseModel):
    name: str

    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Folder name cannot be empty")
        return v


class FolderResponse(BaseModel):
    id: UUID
    name: str
    parent_id: UUID | None
    created_at: datetime
    updated_at: datetime
    project_count: int = 0
    child_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class FolderListResponse(BaseModel):
    folders: list[FolderResponse]
    total: int
