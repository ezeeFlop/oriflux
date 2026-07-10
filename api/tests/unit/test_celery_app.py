"""Seam: the Celery foundation of oriflux_workers (issue #16).

Acceptance: the beat schedule drives the GeoIP refresh (6 h tick, monthly
freshness) and the alert evaluation (60 s) — and every scheduled task name
is actually registered, the classic silent Celery failure.
"""

from oriflux.alerting.evaluator import EVALUATION_INTERVAL_S
from oriflux.config import Settings
from oriflux.workers.celery_app import create_celery
from oriflux.workers.geoip_refresh import RETRY_INTERVAL_S


class TestCeleryApp:
    def test_every_beat_entry_targets_a_registered_task(self) -> None:
        app = create_celery(Settings())

        scheduled = {entry["task"] for entry in app.conf.beat_schedule.values()}
        assert scheduled  # the schedule is not empty
        missing = scheduled - set(app.tasks.keys())
        assert missing == set()

    def test_geoip_and_alert_jobs_are_scheduled_at_their_cadence(self) -> None:
        app = create_celery(Settings())

        schedules = {
            entry["task"]: entry["schedule"] for entry in app.conf.beat_schedule.values()
        }
        assert schedules["oriflux.geoip_refresh"] == RETRY_INTERVAL_S
        assert schedules["oriflux.evaluate_alerts"] == EVALUATION_INTERVAL_S

    def test_broker_is_the_configured_redis(self) -> None:
        settings = Settings(redis_url="redis://example:6390/3")
        app = create_celery(settings)

        assert app.conf.broker_url == "redis://example:6390/3"

    def test_geoip_refresh_is_kicked_at_worker_startup(self) -> None:
        """A cold start (empty geoip volume) must not wait 6 h for the first
        refresh: the worker_ready signal enqueues the task immediately."""
        from celery.signals import worker_ready

        import oriflux.workers.celery_app  # noqa: F401 — connects the handler

        sent: list[str] = []

        class FakeApp:
            def send_task(self, name: str) -> None:
                sent.append(name)

        class FakeSender:
            app = FakeApp()

        worker_ready.send(sender=FakeSender())
        assert sent == ["oriflux.geoip_refresh"]
