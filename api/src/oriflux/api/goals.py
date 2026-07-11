"""Goals CRUD + conversion stats (PRD §5.2, issue #18) — RBAC-guarded.

A goal is declarative: an event name (slug) or a page-path prefix. Admins
manage goals; viewers read them. Conversion counting compiles through the
query registry — event goals filter custom events by event_name, page
goals filter pageviews by url_path prefix, the rate divides by visitors
over the same period. Never bespoke SQL.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, require_role
from oriflux.db.models import Goal, GoalKind, Project, Role, User
from oriflux.models.events import _EVENT_NAME_RE
from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest

router = APIRouter(prefix="/api/v1", tags=["goals"])


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: GoalKind
    target: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def _target_matches_kind(self) -> "GoalIn":
        if self.kind == GoalKind.event and not _EVENT_NAME_RE.match(self.target):
            raise ValueError("event goal target must be an event-name slug")
        if self.kind == GoalKind.page and not self.target.startswith("/"):
            raise ValueError("page goal target must be a path starting with /")
        return self


class GoalOut(BaseModel):
    id: str
    name: str
    kind: GoalKind
    target: str
    conversions: int | None = None
    conversion_rate: float | None = None


def _out(goal: Goal) -> GoalOut:
    return GoalOut(id=str(goal.id), name=goal.name, kind=goal.kind, target=goal.target)


async def _project_or_404(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="unknown project")
    return project


def _goal_request(goal: Goal, period: dict[str, datetime], metric: str) -> QueryRequest:
    project_filter = {"dimension": "project_id", "op": "eq", "value": str(goal.project_id)}
    goal_filter = (
        {"dimension": "event_name", "op": "eq", "value": goal.target}
        if goal.kind == GoalKind.event
        else {"dimension": "page", "op": "prefix", "value": goal.target}
    )
    return QueryRequest.model_validate(
        {"metric": metric, "filters": [project_filter, goal_filter], "period": period}
    )


def _conversions_request(goal: Goal, period: dict[str, datetime]) -> QueryRequest:
    metric = "custom_events" if goal.kind == GoalKind.event else "pageviews"
    return _goal_request(goal, period, metric)


def _converting_visitors_request(goal: Goal, period: dict[str, datetime]) -> QueryRequest:
    # uniq(visitor_hash) both ways: a repeat conversion never inflates the rate
    metric = "custom_event_visitors" if goal.kind == GoalKind.event else "visitors"
    return _goal_request(goal, period, metric)


async def _single_value(request: Request, query: QueryRequest, org_id: str) -> int:
    executor = request.app.state.query_executor()
    sql, params = build_query(query, org_id=org_id)
    rows: list[dict[str, Any]] = await asyncio.to_thread(executor.execute, sql, params)
    value = rows[0]["value"] if rows else 0
    return int(value or 0)


@router.post("/projects/{project_id}/goals", status_code=201)
async def create_goal(
    project_id: uuid.UUID,
    payload: GoalIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GoalOut:
    project = await _project_or_404(session, project_id)
    await require_role(session, user, project.org_id, Role.admin)
    goal = Goal(
        org_id=project.org_id,
        project_id=project.id,
        name=payload.name,
        kind=payload.kind,
        target=payload.target,
    )
    session.add(goal)
    await session.commit()
    return _out(goal)


@router.get("/projects/{project_id}/goals")
async def list_goals(
    project_id: uuid.UUID,
    request: Request,
    start: datetime | None = None,
    end: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[GoalOut]:
    project = await _project_or_404(session, project_id)
    await require_role(session, user, project.org_id, Role.viewer)
    goals = (
        (await session.execute(select(Goal).where(Goal.project_id == project.id)))
        .scalars()
        .all()
    )
    outs = [_out(goal) for goal in goals]

    if start is not None and end is not None and goals:
        period = {"start": start, "end": end}
        org_id = str(project.org_id)
        visitors_query = QueryRequest.model_validate(
            {
                "metric": "visitors",
                "filters": [
                    {"dimension": "project_id", "op": "eq", "value": str(project.id)}
                ],
                "period": period,
            }
        )
        visitors = await _single_value(request, visitors_query, org_id)
        for goal, out in zip(goals, outs, strict=True):
            out.conversions = await _single_value(
                request, _conversions_request(goal, period), org_id
            )
            converting = await _single_value(
                request, _converting_visitors_request(goal, period), org_id
            )
            out.conversion_rate = (
                0.0 if visitors == 0 else round(100 * min(converting, visitors) / visitors, 1)
            )
    return outs


@router.delete("/goals/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    goal = await session.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="unknown goal")
    await require_role(session, user, goal.org_id, Role.admin)
    await session.execute(delete(Goal).where(Goal.id == goal.id))
    await session.commit()
