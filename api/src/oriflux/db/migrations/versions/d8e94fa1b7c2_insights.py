"""insights

Revision ID: d8e94fa1b7c2
Revises: c7f1a25de983
Create Date: 2026-07-11 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e94fa1b7c2'
down_revision: Union[str, Sequence[str], None] = 'c7f1a25de983'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('insights',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('day', sa.String(length=10), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('metric', sa.String(length=64), nullable=False),
    sa.Column('numbers', sa.JSON(), nullable=False),
    sa.Column('query', sa.JSON(), nullable=False),
    sa.Column('text', sa.String(length=1024), nullable=False),
    sa.Column('language', sa.String(length=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'day', 'key')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('insights')
