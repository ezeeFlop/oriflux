"""connectors

Revision ID: a9d0c53fe816
Revises: f8c9e42ab1d3
Create Date: 2026-07-11 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9d0c53fe816'
down_revision: Union[str, Sequence[str], None] = 'f8c9e42ab1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('connectors',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.Enum('stripe', 'lemonsqueezy', name='connectorprovider', native_enum=False, length=16), nullable=False),
    sa.Column('webhook_secret_encrypted', sa.String(length=512), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('connectors')
