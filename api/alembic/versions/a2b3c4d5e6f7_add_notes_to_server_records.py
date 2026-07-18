"""add notes column to server_records

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2025-07-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Free-text practitioner annotations on individual server records.
    # Allows notes like "confirmed decommissioned", "dependency on server X", etc.
    op.add_column('server_records', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('server_records', 'notes')
