"""stripe billing: events ledger + customer id (issue #63)

Revision ID: c9d4a17be250
Revises: b8c2e94fa561
Create Date: 2026-07-11 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d4a17be250'
down_revision: Union[str, Sequence[str], None] = 'b8c2e94fa561'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'stripe_events',
        sa.Column('id', sa.String(length=255), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column(
        'organizations', sa.Column('stripe_customer_id', sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('organizations', 'stripe_customer_id')
    op.drop_table('stripe_events')
