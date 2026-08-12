"""hnsw index on chunk embedding

Revision ID: 37007aac8b1e
Revises: 9b4142dde3f7
Create Date: 2026-08-12 09:56:25.455187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37007aac8b1e'
down_revision: Union[str, Sequence[str], None] = '9b4142dde3f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
