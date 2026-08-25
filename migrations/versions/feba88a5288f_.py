"""empty message

Revision ID: feba88a5288f
Revises: e8255125dea3
Create Date: 2026-08-24 12:34:38.763199

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'feba88a5288f'
down_revision: Union[str, Sequence[str], None] = 'e8255125dea3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Empty on purpose. Autogenerate proposed dropping ix_chunk_content_tsv
    # because the GIN index is created in raw SQL and isn't declared on the
    # model, so it looks like drift. It isn't — the index is intentional.
    pass


def downgrade() -> None:
    # Empty on purpose. Autogenerate proposed dropping ix_chunk_content_tsv
    # because the GIN index is created in raw SQL and isn't declared on the
    # model, so it looks like drift. It isn't — the index is intentional.
    pass