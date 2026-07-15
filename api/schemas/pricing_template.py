"""Pydantic v2 schemas for PricingTemplate."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PricingTemplateResponse(BaseModel):
    id: UUID
    project_id: UUID
    filename: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PricingTemplateStatus(BaseModel):
    has_template: bool
    filename: str | None
    updated_at: datetime | None
