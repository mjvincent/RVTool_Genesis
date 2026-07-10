"""add_llm_settings

Revision ID: a1b2c3d4e5f6
Revises: 25fa967357a9
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '25fa967357a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False, server_default='ollama'),
        # Ollama
        sa.Column('ollama_base_url', sa.String(), nullable=True),
        sa.Column('ollama_model', sa.String(), nullable=True),
        # watsonx.ai
        sa.Column('watsonx_api_key_enc', sa.Text(), nullable=True),
        sa.Column('watsonx_project_id', sa.String(), nullable=True),
        sa.Column('watsonx_url', sa.String(), nullable=True,
                  server_default='https://us-south.ml.cloud.ibm.com'),
        sa.Column('watsonx_model', sa.String(), nullable=True,
                  server_default='ibm/granite-3-8b-instruct'),
        # OpenAI-compatible
        sa.Column('openai_api_key_enc', sa.Text(), nullable=True),
        sa.Column('openai_base_url', sa.String(), nullable=True,
                  server_default='https://api.openai.com'),
        sa.Column('openai_model', sa.String(), nullable=True,
                  server_default='gpt-4o-mini'),
        # Anthropic
        sa.Column('anthropic_api_key_enc', sa.Text(), nullable=True),
        sa.Column('anthropic_model', sa.String(), nullable=True,
                  server_default='claude-3-haiku-20240307'),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    # Seed the default Ollama row so GET /api/settings always returns something
    op.execute(
        "INSERT INTO llm_settings (id, provider, updated_at) "
        "VALUES (1, 'ollama', NOW()) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table('llm_settings')
