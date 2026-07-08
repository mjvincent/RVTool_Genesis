"""SQLAlchemy 2.x ORM models for RVTool Genesis."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    # relationships
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
