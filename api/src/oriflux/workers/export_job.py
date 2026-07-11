"""Daily export dumps (issue #30): every enabled schedule's registry query
runs over its trailing window and lands as CSV in MinIO under
<org>/<name>/<date>.csv. The writer is injectable; failures alert."""

import csv
import io
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import ExportSchedule
from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest

logger = logging.getLogger(__name__)

ObjectWriter = Callable[[str, bytes], None]  # (object_path, payload)


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


def rows_to_csv(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return buffer.getvalue().encode()


async def run_exports(
    session_factory: async_sessionmaker[AsyncSession],
    executor: QueryExecutor,
    write_object: ObjectWriter,
    *,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(tz=UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    dumped = 0
    async with session_factory() as session:
        schedules = [
            (row.org_id, row.name, row.query, row.window_days)
            for row in (
                await session.execute(
                    select(
                        ExportSchedule.org_id,
                        ExportSchedule.name,
                        ExportSchedule.query,
                        ExportSchedule.window_days,
                    ).where(ExportSchedule.enabled.is_(True))
                )
            ).all()
        ]
    for org_id, name, stored_query, window_days in schedules:
        request = QueryRequest.model_validate(
            {
                **stored_query,
                "period": {"start": today - timedelta(days=window_days), "end": today},
            }
        )
        sql, params = build_query(request, org_id=str(org_id))
        rows = executor.execute(sql, params)
        path = f"{org_id}/{name}/{today.date().isoformat()}.csv"
        write_object(path, rows_to_csv(rows[:100_000]))
        dumped += 1
        logger.info("export dumped: %s (%d rows)", path, len(rows))
    return dumped
