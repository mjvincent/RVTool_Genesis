"""Pydantic v2 schemas for Project CRUD."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    folder_id: UUID | None = None
    vpc_region: str | None = "us-south"
    vpc_datacenter: str | None = "us-south-1"
    pvs_region: str | None = "us-south"
    pvs_datacenter: str | None = "dal10"


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    folder_id: UUID | None = None
    vpc_region: str | None = None
    vpc_datacenter: str | None = None
    pvs_region: str | None = None
    pvs_datacenter: str | None = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    folder_id: UUID | None
    vpc_region: str | None
    vpc_datacenter: str | None
    pvs_region: str | None
    pvs_datacenter: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int
