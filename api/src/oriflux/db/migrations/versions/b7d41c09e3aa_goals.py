"""goals

Revision ID: b7d41c09e3aa
Revises: adf76f0a2bfa
Create Date: 2026-07-11 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d41c09e3aa'
down_revision: Union[str, Sequence[str], None] = 'adf76f0a2bfa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('goals',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('kind', sa.Enum('event', 'page', name='goalkind', native_enum=False, length=8), nullable=False),
    sa.Column('target', sa.String(length=512), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('goals')
