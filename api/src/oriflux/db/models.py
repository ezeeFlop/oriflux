"""PostgreSQL metadata models (PRD §8.4): tenancy, RBAC, API keys.

Column types stay dialect-portable (Uuid, non-native enums) so the endpoint
test-suite can run on in-memory SQLite while production uses PostgreSQL 16.
Remaining §8.4 tables (alert_rules, annotations, connectors, billing…) arrive
with their features.
"""

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    pass


class Role(enum.StrEnum):
    owner = "owner"
    admin = "admin"
    viewer = "viewer"


class SourceType(enum.StrEnum):
    web = "web"
    app = "app"
    api = "api"


class KeyScope(enum.StrEnum):
    ingest = "ingest"
    read = "read"


class Plan(Base):
    """A billable plan (issue #60): limits are data, never code. NULL
    monthly_events = unlimited (internal/dogfooding orgs)."""

    __tablename__ = "plans"

    slug: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    monthly_events: Mapped[int | None] = mapped_column(BigInteger)
    stripe_price_id: Mapped[str | None] = mapped_column(String(64))


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    anomalies_muted: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_token_budget: Mapped[int | None] = mapped_column(Integer)  # None → settings default (#33)
    # soft reference to plans.slug (no FK: plans are config-like, and the
    # quota gate fails open on a missing row)
    plan_slug: Mapped[str] = mapped_column(String(32), default="free", server_default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Membership(Base):
    __tablename__ = "memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("org_id", "slug"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    zeus_service: Mapped[str | None] = mapped_column(String(128))  # infra mapping (#29)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    organization: Mapped[Organization] = relationship(back_populates="projects")
    sources: Mapped[list["Source"]] = relationship(back_populates="project")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False, length=8))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="sources")


class GoalKind(enum.StrEnum):
    event = "event"
    page = "page"


class Goal(Base):
    """Declarative conversion goal (PRD §5.2, issue #18): an event name or
    a page-path prefix. Counting compiles through the query registry."""

    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[GoalKind] = mapped_column(Enum(GoalKind, native_enum=False, length=8))
    target: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AnomalyEvent(Base):
    """A zero-config seasonal-baseline detection (issue #27, PRD §5.5)."""

    __tablename__ = "anomaly_events"
    __table_args__ = (UniqueConstraint("project_id", "metric", "window_start"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    metric: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(8))  # drop | spike
    expected: Mapped[float] = mapped_column(Float)
    observed: Mapped[float] = mapped_column(Float)
    deviation_pct: Mapped[float] = mapped_column(Float)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    explanation: Mapped[str] = mapped_column(String(1024), default="")  # grounded diagnosis (#36)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DigestSubscription(Base):
    """Per-user digest preference (issue #26): cadence + language, org-wide."""

    __tablename__ = "digest_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    cadence: Mapped[str] = mapped_column(String(8))  # weekly | monthly
    language: Mapped[str] = mapped_column(String(2), default="fr")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DigestSend(Base):
    """One row per digest actually sent — the idempotence ledger (#26)."""

    __tablename__ = "digest_sends"
    __table_args__ = (UniqueConstraint("subscription_id", "period_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("digest_subscriptions.id"))
    period_key: Mapped[str] = mapped_column(String(16))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ExportSchedule(Base):
    """A saved registry query dumped daily to MinIO as CSV (issue #30)."""

    __tablename__ = "export_schedules"
    __table_args__ = (UniqueConstraint("org_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(64))
    query: Mapped[dict[str, Any]] = mapped_column(JSON)  # QueryRequest minus period
    window_days: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiUsage(Base):
    """One row per SPT Models call (issue #33): the per-org inference
    budget is enforced against the current month's sum, BEFORE each call."""

    __tablename__ = "ai_usage"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    feature: Mapped[str] = mapped_column(String(32))  # ask | insights | explain | digest | segments
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Insight(Base):
    """A daily insight (issue #35): the numbers ARE the record; the prose
    is optional and always grounded in them (query object stored too)."""

    __tablename__ = "insights"
    __table_args__ = (UniqueConstraint("project_id", "day", "key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    day: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(64))
    numbers: Mapped[dict[str, Any]] = mapped_column(JSON)
    query: Mapped[dict[str, Any]] = mapped_column(JSON)
    text: Mapped[str] = mapped_column(String(1024), default="")
    language: Mapped[str] = mapped_column(String(2), default="fr")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ShareToken(Base):
    """A revocable public-dashboard share (issue #41): hashed at rest like
    an API key; the plaintext (ofx_pub_*) is shown once at mint."""

    __tablename__ = "share_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConnectorProvider(enum.StrEnum):
    stripe = "stripe"
    lemonsqueezy = "lemonsqueezy"


class Connector(Base):
    """A billing-webhook connector (issue #24): per project, secret Fernet-
    encrypted at rest (PRD §9)."""

    __tablename__ = "connectors"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    provider: Mapped[ConnectorProvider] = mapped_column(
        Enum(ConnectorProvider, native_enum=False, length=16)
    )
    webhook_secret_encrypted: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AnnotationKind(enum.StrEnum):
    release = "release"
    campaign = "campaign"
    incident = "incident"
    note = "note"


class Annotation(Base):
    """Timeline marker (PRD §5.3, issue #25): release/campaign/incident,
    overlaid on dashboard charts and anchoring before/after comparisons."""

    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[AnnotationKind] = mapped_column(
        Enum(AnnotationKind, native_enum=False, length=12)
    )
    text: Mapped[str] = mapped_column(String(512))
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AlertCondition(enum.StrEnum):
    gt = "gt"
    lt = "lt"


class AlertRule(Base):
    """Threshold alert (PRD §5.5): registry metric + condition + window.

    Evaluated every minute by the workers service through the SAME typed
    query contract as everything else — never bespoke SQL."""

    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255))
    metric: Mapped[str] = mapped_column(String(64))
    filters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    condition: Mapped[AlertCondition] = mapped_column(
        Enum(AlertCondition, native_enum=False, length=4)
    )
    threshold: Mapped[float] = mapped_column(Float)
    window_minutes: Mapped[int] = mapped_column(Integer, default=5)
    slack_webhook_url: Mapped[str | None] = mapped_column(String(1024))
    email: Mapped[str | None] = mapped_column(String(320))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alert_rules.id"))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    value: Mapped[float] = mapped_column(Float)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    # ingest keys are issued per source; read keys are org-wide (source_id NULL)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"))
    scope: Mapped[KeyScope] = mapped_column(Enum(KeyScope, native_enum=False, length=8))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex
    key_prefix: Mapped[str] = mapped_column(String(16))  # displayable identifier
    name: Mapped[str] = mapped_column(String(255), default="")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    source: Mapped[Source | None] = relationship()
