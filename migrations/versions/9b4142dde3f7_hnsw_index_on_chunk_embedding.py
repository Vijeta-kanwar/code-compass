"""hnsw index on chunk embedding

Revision ID: 9b4142dde3f7
Revises: 2f2079004c56
Create Date: 2026-08-12 09:55:26.461926

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b4142dde3f7'
down_revision: Union[str, Sequence[str], None] = '2f2079004c56'
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
