"""anomaly events + org mute switch

Revision ID: d4a92be15c07
Revises: c1e52a77b4d1
Create Date: 2026-07-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a92be15c07'
down_revision: Union[str, Sequence[str], None] = 'c1e52a77b4d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('anomaly_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('metric', sa.String(length=64), nullable=False),
    sa.Column('direction', sa.String(length=8), nullable=False),
    sa.Column('expected', sa.Float(), nullable=False),
    sa.Column('observed', sa.Float(), nullable=False),
    sa.Column('deviation_pct', sa.Float(), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'metric', 'window_start')
    )
    op.add_column('organizations',
                  sa.Column('anomalies_muted', sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('organizations', 'anomalies_muted')
    op.drop_table('anomaly_events')
