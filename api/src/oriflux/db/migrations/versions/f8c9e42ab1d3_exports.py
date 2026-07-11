"""export schedules

Revision ID: f8c9e42ab1d3
Revises: e6b7d31fa2c9
Create Date: 2026-07-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8c9e42ab1d3'
down_revision: Union[str, Sequence[str], None] = 'e6b7d31fa2c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('export_schedules',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('query', sa.JSON(), nullable=False),
    sa.Column('window_days', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'name')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('export_schedules')
