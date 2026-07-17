"""Seam: ClickHouse client lifecycle for the scheduled worker jobs.

Root cause of the prod FD leak (Errno 24 "Too many open files"): the beat
jobs created a clickhouse_connect client on every run (evaluate_alerts every
60 s) and never closed it, exhausting the container's 1024 open-file limit
within a day. `clickhouse_session` guarantees the client is closed on the way
out; `wait_for_clickhouse` closes the clients from its failed retry attempts.
"""

import pytest

from oriflux.config import Settings
from oriflux.storage import clickhouse as ch


class FakeClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.closed = 0
        self.commands: list[str] = []
        self._fail = fail

    def command(self, sql: str, *args: object, **kwargs: object) -> None:
        self.commands.append(sql)
        if self._fail:
            raise ConnectionError("[Errno 24] Too many open files")

    def close(self) -> None:
        self.closed += 1


class TestClickhouseSession:
    def test_closes_client_on_normal_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeClient()
        monkeypatch.setattr(ch, "get_client", lambda settings: client)

        with ch.clickhouse_session(Settings()) as opened:
            assert opened is client
            assert client.closed == 0

        assert client.closed == 1

    def test_closes_client_on_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeClient()
        monkeypatch.setattr(ch, "get_client", lambda settings: client)

        with pytest.raises(ValueError), ch.clickhouse_session(Settings()):
            raise ValueError("boom")

        assert client.closed == 1

    def test_wait_for_clickhouse_closes_failed_attempt_clients(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # two clients whose SELECT 1 fails, then one that succeeds
        seq = [FakeClient(fail=True), FakeClient(fail=True), FakeClient()]
        made: list[FakeClient] = []

        def fake_get_client(settings: Settings) -> FakeClient:
            client = seq[len(made)]
            made.append(client)
            return client

        monkeypatch.setattr(ch, "get_client", fake_get_client)
        monkeypatch.setattr(ch.time, "sleep", lambda _s: None)

        returned = ch.wait_for_clickhouse(Settings(), attempts=3, delay_s=0)

        assert returned is seq[2]
        assert seq[0].closed == 1  # failed attempt was closed — no FD leak
        assert seq[1].closed == 1
        assert seq[2].closed == 0  # the good client stays open for the caller
