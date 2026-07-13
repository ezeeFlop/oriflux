"""annual billing price + cached amounts per plan (#65)

Revision ID: d5f1a9c3b720
Revises: c9d4a17be250
Create Date: 2026-07-13

The annual price is a second cadence of the SAME plan (an org on Pro-annual
is still "pro" for quota and gating), so it is one more column on the plan —
never a separate plan row. The amount/currency are cached from Stripe
(synced by set_stripe_prices) so both the dashboard and the static landing
render live prices without hardcoding a single number.
"""

import sqlalchemy as sa
from alembic import op

revision = "d5f1a9c3b720"
down_revision = "c9d4a17be250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("stripe_price_id_annual", sa.String(length=64), nullable=True))
    op.add_column("plans", sa.Column("amount_cents", sa.Integer(), nullable=True))
    op.add_column("plans", sa.Column("amount_cents_annual", sa.Integer(), nullable=True))
    op.add_column("plans", sa.Column("currency", sa.String(length=3), nullable=True))


def downgrade() -> None:
    op.drop_column("plans", "currency")
    op.drop_column("plans", "amount_cents_annual")
    op.drop_column("plans", "amount_cents")
    op.drop_column("plans", "stripe_price_id_annual")
