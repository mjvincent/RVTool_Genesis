"""Pydantic v2 schemas for Upload and ServerRecord responses."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UploadResponse(BaseModel):
    id: UUID
    project_id: UUID
    filename: str
    status: str
    row_count: int | None
    uploaded_at: datetime
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)


class ServerRecordResponse(BaseModel):
    id: UUID
    upload_id: UUID
    project_id: UUID
    raw_data: dict
    normalized_data: dict | None
    server_type: str | None
    processing_status: str
    is_excluded: bool
    exclusion_reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecordsListResponse(BaseModel):
    records: list[ServerRecordResponse]
    total: int
