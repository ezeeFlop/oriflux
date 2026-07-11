"""backfill alert_rules.project_id from the project_id filter

Rules created before #52 scoped themselves through their filters only;
the column stayed NULL so their events could not deep-link to a project.

Revision ID: a3d5f81c47b2
Revises: f1a7c93be5d8
Create Date: 2026-07-11 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a3d5f81c47b2'
down_revision: Union[str, Sequence[str], None] = 'f1a7c93be5d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID_RE = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def upgrade() -> None:
    """Derive project_id from each rule's project_id eq filter."""
    op.execute(
        f"""
        UPDATE alert_rules AS r
        SET project_id = sub.pid
        FROM (
            SELECT ar.id, (f ->> 'value')::uuid AS pid
            FROM alert_rules AS ar,
                 jsonb_array_elements(ar.filters::jsonb) AS f
            WHERE f ->> 'dimension' = 'project_id'
              AND f ->> 'op' = 'eq'
              AND f ->> 'value' ~ '{_UUID_RE}'
        ) AS sub
        WHERE r.id = sub.id
          AND r.project_id IS NULL
        """
    )


def downgrade() -> None:
    """Data backfill — nothing to undo."""
