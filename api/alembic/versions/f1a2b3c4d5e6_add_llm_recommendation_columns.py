"""add previous_model and recommendation_snoozed_until to llm_settings

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2025-07-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # previous_model: stores the model name before a one-click recommendation upgrade,
    # enabling the "Rollback" button in the Settings UI.
    op.add_column('llm_settings', sa.Column('previous_model', sa.Text(), nullable=True))
    # recommendation_snoozed_until: snooze expiry timestamp — if set and in the future,
    # the recommendation banner is hidden until this time passes.
    op.add_column('llm_settings', sa.Column('recommendation_snoozed_until', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('llm_settings', 'recommendation_snoozed_until')
    op.drop_column('llm_settings', 'previous_model')
