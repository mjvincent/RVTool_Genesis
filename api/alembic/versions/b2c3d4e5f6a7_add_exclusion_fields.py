"""add_exclusion_fields_to_server_records

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-01-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'server_records',
        sa.Column('is_excluded', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'server_records',
        sa.Column('exclusion_reason', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('server_records', 'exclusion_reason')
    op.drop_column('server_records', 'is_excluded')
