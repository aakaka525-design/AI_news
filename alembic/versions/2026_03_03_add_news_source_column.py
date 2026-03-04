"""add news source column

Revision ID: a1b2c3d4e5f6
Revises: 86e5b3738ff0
Create Date: 2026-03-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str]] = '86e5b3738ff0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('news', sa.Column('source', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('news', 'source')
