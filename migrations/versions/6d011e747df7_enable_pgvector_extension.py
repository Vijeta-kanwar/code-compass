"""enable pgvector extension

Revision ID: 6d011e747df7
Revises: 
Create Date: 2026-08-07 20:00:29.841869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d011e747df7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # vector_cosine_ops must match the operator used at query time (<=>).
    # Pair it with <-> or <#> and the planner silently ignores the index.
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
