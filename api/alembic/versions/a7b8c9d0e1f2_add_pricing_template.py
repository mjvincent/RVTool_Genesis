"""add pricing_templates table

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2025-07-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create table only if it doesn't already exist (idempotent).
    # The table may have been created manually or by a prior run of this migration
    # before the revision ID conflict was resolved.
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'pricing_templates'"
        )
    )
    if result.fetchone() is None:
        op.create_table(
            'pricing_templates',
            sa.Column('id',         sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('project_id', sa.dialects.postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('projects.id', ondelete='CASCADE'),
                      nullable=False, unique=True),
            sa.Column('filename',   sa.String(),      nullable=False),
            sa.Column('file_data',  sa.LargeBinary(), nullable=False),
            sa.Column('created_at', sa.DateTime(),    nullable=False),
            sa.Column('updated_at', sa.DateTime(),    nullable=False),
        )


def downgrade() -> None:
    op.drop_table('pricing_templates')
