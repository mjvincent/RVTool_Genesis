"""SQLAlchemy 2.x ORM models for RVTool Genesis."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class Folder(Base):
    """Hierarchical folder for grouping projects.

    Max depth = 2 (root → customer → engagement).
    A NULL parent_id means the folder lives at root level.
    """
    __tablename__ = "folders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    # relationships
    parent: Mapped["Folder | None"] = relationship(
        "Folder", remote_side="Folder.id", back_populates="children"
    )
    children: Mapped[list["Folder"]] = relationship(
        "Folder", back_populates="parent", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="folder"
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional folder grouping — NULL means project lives at root (ungrouped)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True
    )
    # IBM Cloud VPC target region — set at project creation, used by VPC Calculator export
    vpc_region: Mapped[str | None] = mapped_column(String, nullable=True, default="us-south")
    vpc_datacenter: Mapped[str | None] = mapped_column(String, nullable=True, default="us-south-1")
    # IBM PowerVS target region/datacenter — independent from VPC (uses short names e.g. dal10)
    pvs_region: Mapped[str | None] = mapped_column(String, nullable=True, default="us-south")
    pvs_datacenter: Mapped[str | None] = mapped_column(String, nullable=True, default="dal10")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    # relationships
    folder: Mapped["Folder | None"] = relationship(back_populates="projects")
    uploads: Mapped[list["Upload"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    server_records: Mapped[list["ServerRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    assumptions: Mapped[list["Assumption"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    rvtools_exports: Mapped[list["RVToolsExport"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    assumptions_exports: Mapped[list["AssumptionsExport"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    # One IBM Price Estimator template per project (optional, upserted on upload)
    pricing_template: Mapped["PricingTemplate | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    raw_file: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(default=_utcnow)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    project: Mapped["Project"] = relationship(back_populates="uploads")
    server_records: Mapped[list["ServerRecord"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan"
    )


class ServerRecord(Base):
    __tablename__ = "server_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    server_type: Mapped[str | None] = mapped_column(String, nullable=True)
    processing_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Exclusion — user-controlled, survives page refresh
    is_excluded: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Practitioner annotations — free-text notes that don't fit the assumption system
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    # relationships
    upload: Mapped["Upload"] = relationship(back_populates="server_records")
    project: Mapped["Project"] = relationship(back_populates="server_records")
    assumptions: Mapped[list["Assumption"]] = relationship(
        back_populates="server_record", cascade="all, delete-orphan"
    )


class Assumption(Base):
    __tablename__ = "assumptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    server_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("server_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    assumed_value: Mapped[str] = mapped_column(Text, nullable=False)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    # relationships
    server_record: Mapped["ServerRecord"] = relationship(back_populates="assumptions")
    project: Mapped["Project"] = relationship(back_populates="assumptions")


class RVToolsExport(Base):
    __tablename__ = "rvtools_exports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(default=_utcnow)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    record_count: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")

    # relationships
    project: Mapped["Project"] = relationship(back_populates="rvtools_exports")


class AssumptionsExport(Base):
    __tablename__ = "assumptions_exports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(default=_utcnow)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    assumption_count: Mapped[int | None] = mapped_column(nullable=True)

    # relationships
    project: Mapped["Project"] = relationship(back_populates="assumptions_exports")


class LLMSettings(Base):
    """Single-row settings table (id=1 always) for LLM provider configuration.

    API keys are stored encrypted (AES-256 Fernet) — never plaintext.
    """
    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    provider: Mapped[str] = mapped_column(String, nullable=False, default="ollama")

    # Ollama overrides (optional — falls back to env vars)
    ollama_base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    ollama_model: Mapped[str | None] = mapped_column(String, nullable=True)

    # IBM watsonx.ai
    watsonx_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    watsonx_project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    watsonx_url: Mapped[str | None] = mapped_column(
        String, nullable=True, default="https://us-south.ml.cloud.ibm.com"
    )
    watsonx_model: Mapped[str | None] = mapped_column(
        String, nullable=True, default="ibm/granite-3-8b-instruct"
    )

    # OpenAI-compatible
    openai_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    openai_base_url: Mapped[str | None] = mapped_column(
        String, nullable=True, default="https://api.openai.com"
    )
    openai_model: Mapped[str | None] = mapped_column(
        String, nullable=True, default="gpt-4o-mini"
    )

    # Anthropic
    anthropic_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    anthropic_model: Mapped[str | None] = mapped_column(
        String, nullable=True, default="claude-3-haiku-20240307"
    )

    # Docker Model Runner (OpenAI-compatible inference endpoint, port 9545)
    dmr_base_url: Mapped[str | None] = mapped_column(
        String, nullable=True, default="http://host.docker.internal:9545"
    )
    dmr_model: Mapped[str | None] = mapped_column(String, nullable=True)

    # Model recommendation rollback support
    previous_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_snoozed_until: Mapped[datetime | None] = mapped_column(nullable=True)

    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class PricingTemplate(Base):
    """IBM Price Estimator workbook stored per project.

    Stores the raw bytes of the uploaded IBM Power Virtual Server Price Estimator
    Excel file. One per project (upsert pattern). The filler service writes only
    the yellow input cells into this template, preserving all formulas.
    """
    __tablename__ = "pricing_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, unique=True,   # one per project
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    # relationships
    project: Mapped["Project"] = relationship(back_populates="pricing_template")
