"""add processing_jobs table

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-07-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'h2i3j4k5l6m7'
down_revision = 'g1h2i3j4k5l6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'processing_jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True),
                  sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('total_records', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_records', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index(
        'ix_processing_jobs_project_status',
        'processing_jobs',
        ['project_id', 'status'],
    )


def downgrade() -> None:
    op.drop_index('ix_processing_jobs_project_status', table_name='processing_jobs')
    op.drop_table('processing_jobs')
