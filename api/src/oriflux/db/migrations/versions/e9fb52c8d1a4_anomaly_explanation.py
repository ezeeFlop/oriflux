"""anomaly explanation

Revision ID: e9fb52c8d1a4
Revises: d8e94fa1b7c2
Create Date: 2026-07-11 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9fb52c8d1a4'
down_revision: Union[str, Sequence[str], None] = 'd8e94fa1b7c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('anomaly_events',
                  sa.Column('explanation', sa.String(length=1024), nullable=False,
                            server_default=''))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('anomaly_events', 'explanation')
