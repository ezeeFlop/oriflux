"""Explained alerts & anomalies (issue #36, PRD §6).

Statistics first: the metric is decomposed over registry dimensions to
rank contributors; SPT Models only PHRASES the ranked numbers. An
explanation is always optional — its failure never blocks the base
notification or detection.
"""

import json
import logging
from datetime import datetime
from typing import Any, Protocol

from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest

logger = logging.getLogger(__name__)

_EVENT_DIMENSIONS = ("country", "page", "referrer", "device")
_API_DIMENSIONS = ("endpoint", "status_class", "consumer", "country")


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


class ChatGateway(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def chat(self, org_id: str, *, feature: str, messages: list[dict[str, str]],
                   temperature: float = 0.2) -> str: ...


def dimensions_for(metric: str) -> tuple[str, ...]:
    return _API_DIMENSIONS if metric.startswith("api_") else _EVENT_DIMENSIONS


def rank_contributors(
    executor: QueryExecutor,
    *,
    org_id: str,
    project_id: str,
    metric: str,
    window: tuple[datetime, datetime],
    dimensions: tuple[str, ...] | None = None,
    top: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Registry-only decomposition: metric grouped by each dimension."""
    contributors: dict[str, list[dict[str, Any]]] = {}
    for dimension in dimensions or dimensions_for(metric):
        try:
            request = QueryRequest.model_validate({
                "metric": metric,
                "dimensions": [dimension],
                "filters": [{"dimension": "project_id", "op": "eq", "value": project_id}],
                "period": {"start": window[0], "end": window[1]},
            })
        except Exception:  # noqa: BLE001 — dimension not valid for this metric
            continue
        sql, params = build_query(request, org_id=org_id)
        rows = executor.execute(sql, params)
        ranked = sorted(rows, key=lambda r: float(r.get("value") or 0), reverse=True)
        contributors[dimension] = ranked[:top]
    return contributors


async def explain_movement(
    gateway: ChatGateway,
    executor: QueryExecutor,
    *,
    org_id: str,
    project_id: str,
    metric: str,
    window: tuple[datetime, datetime],
    headline: str,
    annotations: list[str] | None = None,
) -> str:
    """One short diagnosis, grounded in ranked contributors. '' on any failure."""
    if not getattr(gateway, "enabled", False):
        return ""
    try:
        contributors = rank_contributors(
            executor, org_id=org_id, project_id=project_id, metric=metric, window=window
        )
        prompt = {
            "movement": headline,
            "contributors": contributors,
            "nearby_releases": annotations or [],
        }
        return await gateway.chat(
            org_id,
            feature="explain",
            messages=[
                {"role": "system", "content": (
                    "Diagnose this metric movement in 1-2 sentences (French), citing "
                    "ONLY the provided contributor numbers and releases. No speculation."
                )},
                {"role": "user", "content": json.dumps(prompt, default=str)},
            ],
        )
    except Exception:  # noqa: BLE001 — explanations are strictly optional
        logger.warning("explanation failed", exc_info=True)
        return ""
