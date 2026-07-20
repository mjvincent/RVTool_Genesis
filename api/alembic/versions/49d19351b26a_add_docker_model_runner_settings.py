"""add docker model runner settings

Revision ID: 49d19351b26a
Revises: a2b3c4d5e6f7
Create Date: 2026-07-20 17:44:36.241756+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49d19351b26a'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('llm_settings', sa.Column('dmr_base_url', sa.String(), nullable=True))
    op.add_column('llm_settings', sa.Column('dmr_model', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('llm_settings', 'dmr_model')
    op.drop_column('llm_settings', 'dmr_base_url')
