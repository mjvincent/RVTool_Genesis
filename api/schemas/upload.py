"""Pydantic v2 schemas for Upload and ServerRecord responses."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UploadResponse(BaseModel):
    id: UUID
    project_id: UUID
    filename: str
    status: str
    row_count: int | None
    uploaded_at: datetime
    error_message: str | None
    columns: list[str] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ServerRecordResponse(BaseModel):
    id: UUID
    upload_id: UUID
    project_id: UUID
    raw_data: dict
    normalized_data: dict | None
    server_type: str | None
    processing_status: str
    error_message: str | None
    is_excluded: bool
    exclusion_reason: str | None
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecordsListResponse(BaseModel):
    records: list[ServerRecordResponse]
    total: int
