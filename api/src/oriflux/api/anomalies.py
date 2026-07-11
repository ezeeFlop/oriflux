"""Anomaly feed (issue #27): the dashboard lists recent detections."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_session, require_read_org
from oriflux.db.models import AnomalyEvent, Insight, Project

router = APIRouter(prefix="/api/v1", tags=["anomalies"])


class AnomalyOut(BaseModel):
    id: str
    project_id: str
    project_name: str
    metric: str
    direction: str
    expected: float
    observed: float
    deviation_pct: float
    window_start: datetime
    explanation: str = ""


@router.get("/orgs/{org_id}/insights", operation_id="get_insights",
            summary="Daily insights feed (numbers + grounded prose)")
async def list_insights(
    org_id: uuid.UUID,
    limit: int = 20,
    caller_org: str = Depends(require_read_org),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    if str(org_id) != caller_org:
        raise HTTPException(status_code=403, detail="organization mismatch")
    rows = (
        await session.execute(
            select(Insight, Project.name)
            .join(Project, Insight.project_id == Project.id)
            .where(Insight.org_id == org_id)
            .order_by(Insight.created_at.desc())
            .limit(min(limit, 100))
        )
    ).all()
    return [
        {
            "id": str(insight.id),
            "project_name": project_name,
            "day": insight.day,
            "kind": insight.kind,
            "metric": insight.metric,
            "numbers": insight.numbers,
            "query": insight.query,
            "text": insight.text,
        }
        for insight, project_name in rows
    ]


@router.get("/orgs/{org_id}/anomalies")
async def list_anomalies(
    org_id: uuid.UUID,
    limit: int = 20,
    caller_org: str = Depends(require_read_org),
    session: AsyncSession = Depends(get_session),
) -> list[AnomalyOut]:
    if str(org_id) != caller_org:
        raise HTTPException(status_code=403, detail="organization mismatch")
    rows = (
        await session.execute(
            select(AnomalyEvent, Project.name)
            .join(Project, AnomalyEvent.project_id == Project.id)
            .where(AnomalyEvent.org_id == org_id)
            .order_by(AnomalyEvent.window_start.desc())
            .limit(min(limit, 100))
        )
    ).all()
    return [
        AnomalyOut(
            id=str(event.id),
            project_id=str(event.project_id),
            project_name=project_name,
            metric=event.metric,
            direction=event.direction,
            expected=event.expected,
            observed=event.observed,
            deviation_pct=event.deviation_pct,
            window_start=event.window_start,
            explanation=event.explanation,
        )
        for event, project_name in rows
    ]
