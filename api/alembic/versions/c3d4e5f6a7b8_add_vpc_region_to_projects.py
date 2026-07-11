"""add vpc_region and vpc_datacenter to projects

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-10 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('vpc_region', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('vpc_datacenter', sa.String(), nullable=True))
    # Default existing projects to us-south / us-south-1
    op.execute("UPDATE projects SET vpc_region = 'us-south', vpc_datacenter = 'us-south-1' WHERE vpc_region IS NULL")


def downgrade() -> None:
    op.drop_column('projects', 'vpc_datacenter')
    op.drop_column('projects', 'vpc_region')
