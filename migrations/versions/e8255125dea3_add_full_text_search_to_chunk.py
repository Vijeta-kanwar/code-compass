"""add full text search to chunk

Revision ID: e8255125dea3
Revises: 37007aac8b1e
Create Date: 2026-08-24 12:25:46.898847

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8255125dea3'
down_revision: Union[str, Sequence[str], None] = '37007aac8b1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chunk ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )

    op.execute(
        "CREATE INDEX ix_chunk_content_tsv "
        "ON chunk USING gin (content_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_content_tsv")
    op.execute("ALTER TABLE chunk DROP COLUMN IF EXISTS content_tsv")