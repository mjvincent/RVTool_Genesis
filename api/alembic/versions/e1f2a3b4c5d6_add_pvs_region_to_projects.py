"""add pvs_region and pvs_datacenter to projects

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('pvs_region', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('pvs_datacenter', sa.String(), nullable=True))
    # Default existing rows to us-south / dal10
    op.execute("UPDATE projects SET pvs_region = 'us-south', pvs_datacenter = 'dal10' WHERE pvs_region IS NULL")


def downgrade() -> None:
    op.drop_column('projects', 'pvs_datacenter')
    op.drop_column('projects', 'pvs_region')
