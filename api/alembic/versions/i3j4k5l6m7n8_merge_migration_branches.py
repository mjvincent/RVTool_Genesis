"""merge migration branches: pricing/notes/dmr branch + audit_log/processing_jobs branch

Revision ID: i3j4k5l6m7n8
Revises: 49d19351b26a, h2i3j4k5l6m7
Create Date: 2026-07-21 00:00:01.000000

This merge resolves the two migration heads that diverged from f1a2b3c4d5e6:
  Branch A: f1a2 → a7b8 (pricing_template) → a2b3 (notes) → 49d1 (docker_model_runner)
  Branch B: f1a2 → g1h2 (audit_log) → h2i3 (processing_jobs)
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'i3j4k5l6m7n8'
down_revision = ('49d19351b26a', 'h2i3j4k5l6m7')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
