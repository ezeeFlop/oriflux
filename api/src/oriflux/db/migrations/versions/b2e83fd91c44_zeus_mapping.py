"""project zeus service mapping

Revision ID: b2e83fd91c44
Revises: a9d0c53fe816
Create Date: 2026-07-11 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2e83fd91c44'
down_revision: Union[str, Sequence[str], None] = 'a9d0c53fe816'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('projects', sa.Column('zeus_service', sa.String(length=128), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'zeus_service')
