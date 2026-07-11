"""plans table + organizations.plan_slug (issue #60)

Seeds free/pro/scale with default quotas (data, adjustable in place) and an
unlimited `internal` plan; every pre-existing organization moves to
`internal` so dogfooding never hits a quota it never signed up for.

Revision ID: b8c2e94fa561
Revises: a3d5f81c47b2
Create Date: 2026-07-11 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c2e94fa561'
down_revision: Union[str, Sequence[str], None] = 'a3d5f81c47b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'plans',
        sa.Column('slug', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('monthly_events', sa.BigInteger(), nullable=True),
        sa.Column('stripe_price_id', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('slug'),
    )
    op.execute(
        """
        INSERT INTO plans (slug, name, monthly_events, stripe_price_id) VALUES
            ('free', 'Free', 100000, NULL),
            ('pro', 'Pro', 1000000, NULL),
            ('scale', 'Scale', 10000000, NULL),
            ('internal', 'Internal', NULL, NULL)
        """
    )
    op.add_column(
        'organizations',
        sa.Column('plan_slug', sa.String(length=32), nullable=False, server_default='free'),
    )
    op.execute("UPDATE organizations SET plan_slug = 'internal'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('organizations', 'plan_slug')
    op.drop_table('plans')
