"""add folders table and folder_id to projects

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a7b8
Create Date: 2026-07-14 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd1e2f3a4b5c6'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create folders table (self-referential, max 2 levels enforced in API)
    op.create_table(
        'folders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['folders.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_folders_parent_id', 'folders', ['parent_id'])

    # Add folder_id FK to projects (NULL = root / ungrouped)
    op.add_column('projects', sa.Column('folder_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_projects_folder_id', 'projects', 'folders',
        ['folder_id'], ['id'], ondelete='SET NULL'
    )
    op.create_index('ix_projects_folder_id', 'projects', ['folder_id'])


def downgrade() -> None:
    op.drop_index('ix_projects_folder_id', table_name='projects')
    op.drop_constraint('fk_projects_folder_id', 'projects', type_='foreignkey')
    op.drop_column('projects', 'folder_id')
    op.drop_index('ix_folders_parent_id', table_name='folders')
    op.drop_table('folders')
