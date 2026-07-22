"""add audit_log table

Revision ID: g1h2i3j4k5l6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'g1h2i3j4k5l6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True),
                  sa.ForeignKey('projects.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('operation', sa.String(length=80), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('record_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'),
                  nullable=False),
    )
    op.create_index(
        'ix_audit_log_project_id_created_at',
        'audit_log',
        ['project_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_audit_log_project_id_created_at', table_name='audit_log')
    op.drop_table('audit_log')
