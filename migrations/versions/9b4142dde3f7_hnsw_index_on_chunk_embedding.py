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
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
