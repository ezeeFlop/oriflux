"""Seams: SSRF webhook validation and the alert state machine (issue #11).

State machine contract: a breach fires exactly one notification; the same
breach persisting stays silent (cooldown/dedup); recovery notifies once and
closes the event. Evaluation compiles through the query registry only.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.alerting.evaluator import Evaluator
from oriflux.db.models import AlertEvent, AlertRule, Organization
from oriflux.security.ssrf import validate_public_url


class TestSsrfValidation:
    @pytest.mark.parametrize(
        "url",
        [
            "http://hooks.slack.com/x",  # not https
            "https://127.0.0.1/hook",
            "https://localhost/hook",
            "https://10.0.0.8/hook",
            "https://192.168.1.10/hook",
            "https://169.254.169.254/latest/meta-data",  # cloud metadata
            "https://[::1]/hook",
            "ftp://hooks.slack.com/x",
            "https://",
        ],
    )
    def test_internal_and_non_https_urls_are_rejected(self, url: str) -> None:
        with pytest.raises(ValueError):
            validate_public_url(url)

    def test_public_https_urls_pass(self) -> None:
        validate_public_url("https://hooks.slack.com/services/T000/B000/xyz")


class TestNotifierRetry:
    def test_slack_delivery_retries_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from oriflux.alerting import notify as notify_module
        from oriflux.alerting.notify import AlertNotifier
        from oriflux.config import Settings

        attempts: list[str] = []

        class FakeResponse:
            def raise_for_status(self) -> None:
                pass

        def flaky_post(url: str, **kwargs: Any) -> FakeResponse:
            attempts.append(url)
            if len(attempts) < 3:
                raise ConnectionError("slack hiccup")
            return FakeResponse()

        monkeypatch.setattr(notify_module.requests, "post", flaky_post)
        monkeypatch.setattr(notify_module.time, "sleep", lambda _: None)

        rule = AlertRule(
            org_id=uuid.uuid4(), name="r", metric="pageviews", filters=[],
            condition="gt", threshold=1.0, window_minutes=5,
            slack_webhook_url="https://hooks.example/x",
        )
        notifier = AlertNotifier(Settings(allow_private_webhooks=True))
        notifier.notify(rule, kind="firing", value=9.0)  # must not raise
        assert len(attempts) == 3  # failed, failed, delivered

    def test_exhausted_retries_are_logged_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from oriflux.alerting import notify as notify_module
        from oriflux.alerting.notify import AlertNotifier
        from oriflux.config import Settings

        def always_down(url: str, **kwargs: Any) -> Any:
            raise ConnectionError("down")

        monkeypatch.setattr(notify_module.requests, "post", always_down)
        monkeypatch.setattr(notify_module.time, "sleep", lambda _: None)
        rule = AlertRule(
            org_id=uuid.uuid4(), name="r", metric="pageviews", filters=[],
            condition="gt", threshold=1.0, window_minutes=5,
            slack_webhook_url="https://hooks.example/x",
        )
        AlertNotifier(Settings(allow_private_webhooks=True)).notify(
            rule, kind="firing", value=9.0
        )


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []  # (kind, text)

    def notify(self, rule: AlertRule, *, kind: str, value: float, extra: str = "") -> None:
        self.messages.append((kind, f"{rule.name}: {value}"))


class ScriptedExecutor:
    """Returns scripted metric values, records the SQL it was given."""

    def __init__(self) -> None:
        self.value = 0.0
        self.sqls: list[str] = []

    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.sqls.append(sql)
        return [{"value": self.value}]


async def seed_rule(factory: async_sessionmaker[AsyncSession]) -> AlertRule:
    async with factory() as session:
        org = Organization(slug=f"alerts-{uuid.uuid4().hex[:6]}", name="x")
        session.add(org)
        await session.flush()
        rule = AlertRule(
            org_id=org.id,
            name="5xx over 2%",
            metric="api_error_rate_5xx",
            filters=[],
            condition="gt",
            threshold=2.0,
            window_minutes=5,
        )
        session.add(rule)
        await session.commit()
        return rule


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def executor() -> ScriptedExecutor:
    return ScriptedExecutor()


def make_evaluator(
    factory: async_sessionmaker[AsyncSession],
    executor: ScriptedExecutor,
    notifier: RecordingNotifier,
) -> Evaluator:
    return Evaluator(factory, executor, notifier)


class TestStateMachine:
    async def test_a_breach_fires_exactly_once(
        self,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        executor: ScriptedExecutor,
        notifier: RecordingNotifier,
    ) -> None:
        rule = await seed_rule(db_sessionmaker)
        evaluator = make_evaluator(db_sessionmaker, executor, notifier)

        executor.value = 7.5  # > 2.0 → breach
        await evaluator.run_once(now=datetime(2026, 7, 10, 12, 0, tzinfo=UTC))
        await evaluator.run_once(now=datetime(2026, 7, 10, 12, 1, tzinfo=UTC))
        await evaluator.run_once(now=datetime(2026, 7, 10, 12, 2, tzinfo=UTC))

        assert [k for k, _ in notifier.messages] == ["firing"]
        async with db_sessionmaker() as session:
            events = (await session.execute(select(AlertEvent))).scalars().all()
            assert len(events) == 1
            assert events[0].resolved_at is None
            assert events[0].value == 7.5
            assert str(events[0].rule_id) == str(rule.id)

    async def test_recovery_notifies_once_and_closes_the_event(
        self,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        executor: ScriptedExecutor,
        notifier: RecordingNotifier,
    ) -> None:
        await seed_rule(db_sessionmaker)
        evaluator = make_evaluator(db_sessionmaker, executor, notifier)

        executor.value = 7.5
        await evaluator.run_once(now=datetime(2026, 7, 10, 12, 0, tzinfo=UTC))
        executor.value = 0.2  # back to normal
        await evaluator.run_once(now=datetime(2026, 7, 10, 12, 1, tzinfo=UTC))
        await evaluator.run_once(now=datetime(2026, 7, 10, 12, 2, tzinfo=UTC))

        assert [k for k, _ in notifier.messages] == ["firing", "resolved"]
        async with db_sessionmaker() as session:
            event = (await session.execute(select(AlertEvent))).scalar_one()
            assert event.resolved_at is not None

    async def test_no_breach_means_no_noise(
        self,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        executor: ScriptedExecutor,
        notifier: RecordingNotifier,
    ) -> None:
        await seed_rule(db_sessionmaker)
        executor.value = 0.1
        await make_evaluator(db_sessionmaker, executor, notifier).run_once(
            now=datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        )
        assert notifier.messages == []

    async def test_disabled_rules_are_skipped(
        self,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        executor: ScriptedExecutor,
        notifier: RecordingNotifier,
    ) -> None:
        rule = await seed_rule(db_sessionmaker)
        async with db_sessionmaker() as session:
            db_rule = await session.get(AlertRule, rule.id)
            assert db_rule is not None
            db_rule.enabled = False
            await session.commit()
        executor.value = 99.0
        await make_evaluator(db_sessionmaker, executor, notifier).run_once(
            now=datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        )
        assert notifier.messages == []

    async def test_evaluation_compiles_through_the_registry(
        self,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        executor: ScriptedExecutor,
        notifier: RecordingNotifier,
    ) -> None:
        await seed_rule(db_sessionmaker)
        executor.value = 9.0
        await make_evaluator(db_sessionmaker, executor, notifier).run_once(
            now=datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        )
        assert executor.sqls
        assert "FROM api_minutely FINAL" in executor.sqls[0]  # registry fragment, not bespoke

    async def test_a_notifier_crash_does_not_kill_the_evaluator(
        self,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        executor: ScriptedExecutor,
    ) -> None:
        await seed_rule(db_sessionmaker)

        class ExplodingNotifier:
            def notify(self, rule: AlertRule, *, kind: str, value: float, extra: str = "") -> None:
                raise ConnectionError("slack down")

        executor.value = 9.0
        evaluator = Evaluator(db_sessionmaker, executor, ExplodingNotifier())
        await evaluator.run_once(now=datetime(2026, 7, 10, 12, 0, tzinfo=UTC))  # must not raise
