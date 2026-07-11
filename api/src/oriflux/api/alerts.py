"""Alert rules CRUD (issue #11) — org-scoped, RBAC-guarded.

Admins manage rules; viewers read rules and events. Rule metric/filters
are validated by dry-compiling a registry query at save time, so a rule
that stores successfully can always be evaluated. Webhook URLs pass SSRF
validation (PRD §9). The dashboard UI for this arrives with issue #7.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, require_role
from oriflux.db.models import AlertCondition, AlertEvent, AlertRule, Role, User
from oriflux.query.models import Filter, QueryRequest
from oriflux.security.ssrf import validate_public_url

router = APIRouter(prefix="/api/v1", tags=["alerts"])


class AlertRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    metric: str
    filters: list[Filter] = Field(default_factory=list)
    condition: AlertCondition
    threshold: float
    window_minutes: int = Field(default=5, ge=1, le=1440)
    slack_webhook_url: str | None = None
    email: str | None = Field(default=None, max_length=320)


class AlertRuleOut(BaseModel):
    id: str
    name: str
    metric: str
    filters: list[dict[str, Any]]
    condition: AlertCondition
    threshold: float
    window_minutes: int
    slack_webhook_url: str | None
    email: str | None
    enabled: bool


class AlertRulePatch(BaseModel):
    name: str | None = None
    threshold: float | None = None
    window_minutes: int | None = Field(default=None, ge=1, le=1440)
    enabled: bool | None = None


class AlertEventOut(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    # the rule's scope, so the UI can link an event to its project (#47)
    project_id: str | None
    metric: str
    value: float
    fired_at: datetime
    resolved_at: datetime | None


def _validate_rule(payload: AlertRuleIn) -> None:
    try:
        # dry-compile through the registry: same schema as /api/v1/query
        QueryRequest.model_validate(
            {
                "metric": payload.metric,
                "filters": [f.model_dump() for f in payload.filters],
                "period": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
            }
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.slack_webhook_url is not None:
        try:
            validate_public_url(payload.slack_webhook_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


def _out(rule: AlertRule) -> AlertRuleOut:
    return AlertRuleOut(
        id=str(rule.id),
        name=rule.name,
        metric=rule.metric,
        filters=rule.filters,
        condition=rule.condition,
        threshold=rule.threshold,
        window_minutes=rule.window_minutes,
        slack_webhook_url=rule.slack_webhook_url,
        email=rule.email,
        enabled=rule.enabled,
    )


@router.post("/orgs/{org_id}/alert-rules", status_code=201)
async def create_rule(
    org_id: uuid.UUID,
    payload: AlertRuleIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertRuleOut:
    await require_role(session, user, org_id, Role.admin)
    _validate_rule(payload)
    rule = AlertRule(
        org_id=org_id,
        name=payload.name,
        metric=payload.metric,
        filters=[f.model_dump() for f in payload.filters],
        condition=payload.condition,
        threshold=payload.threshold,
        window_minutes=payload.window_minutes,
        slack_webhook_url=payload.slack_webhook_url,
        email=payload.email,
    )
    session.add(rule)
    await session.commit()
    return _out(rule)


@router.get("/orgs/{org_id}/alert-rules")
async def list_rules(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AlertRuleOut]:
    await require_role(session, user, org_id, Role.viewer)
    rules = (
        (await session.execute(select(AlertRule).where(AlertRule.org_id == org_id)))
        .scalars()
        .all()
    )
    return [_out(r) for r in rules]


async def _rule_for_admin(
    session: AsyncSession, user: User, rule_id: uuid.UUID
) -> AlertRule:
    rule = await session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    await require_role(session, user, rule.org_id, Role.admin)
    return rule


@router.patch("/alert-rules/{rule_id}")
async def patch_rule(
    rule_id: uuid.UUID,
    payload: AlertRulePatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertRuleOut:
    rule = await _rule_for_admin(session, user, rule_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    await session.commit()
    return _out(rule)


@router.delete("/alert-rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    rule = await _rule_for_admin(session, user, rule_id)
    await session.execute(delete(AlertEvent).where(AlertEvent.rule_id == rule.id))
    await session.delete(rule)
    await session.commit()


@router.get("/orgs/{org_id}/alert-events", operation_id="get_alerts",
            summary="Alert events (firing/resolved) for the organization")
async def list_events(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AlertEventOut]:
    await require_role(session, user, org_id, Role.viewer)
    rows = (
        await session.execute(
            select(AlertEvent, AlertRule.name, AlertRule.project_id, AlertRule.metric)
            .join(AlertRule, AlertRule.id == AlertEvent.rule_id)
            .where(AlertEvent.org_id == org_id)
            .order_by(AlertEvent.fired_at.desc())
            .limit(100)
        )
    ).all()
    return [
        AlertEventOut(
            id=str(event.id),
            rule_id=str(event.rule_id),
            rule_name=rule_name,
            project_id=str(project_id) if project_id is not None else None,
            metric=metric,
            value=event.value,
            fired_at=event.fired_at,
            resolved_at=event.resolved_at,
        )
        for event, rule_name, project_id, metric in rows
    ]
