"""Seam: cookieless sessionization at ingest (issue #6).

A session is a visitor's activity with < 30 min between events, tracked as
a short-lived Redis mapping keyed on the (already daily-rotating,
pseudonymous) visitor hash. No client-side identifier is ever involved.
"""

import asyncio

from fakeredis import FakeAsyncRedis

from oriflux.enrichment.sessions import SESSION_GAP_S, SessionTracker


class TestSessionTracker:
    async def test_same_visitor_within_the_gap_shares_a_session(self) -> None:
        tracker = SessionTracker(FakeAsyncRedis())
        first = await tracker.session_for("visitor-a")
        second = await tracker.session_for("visitor-a")
        assert first == second

    async def test_distinct_visitors_get_distinct_sessions(self) -> None:
        tracker = SessionTracker(FakeAsyncRedis())
        assert await tracker.session_for("visitor-a") != await tracker.session_for("visitor-b")

    async def test_a_new_session_starts_after_the_gap(self) -> None:
        redis = FakeAsyncRedis()
        tracker = SessionTracker(redis)
        first = await tracker.session_for("visitor-a")
        # simulate the 30-min gap: the mapping expired
        await redis.flushall()
        second = await tracker.session_for("visitor-a")
        assert first != second

    async def test_each_event_slides_the_expiry_window(self) -> None:
        redis = FakeAsyncRedis()
        tracker = SessionTracker(redis)
        await tracker.session_for("visitor-a")
        keys = await redis.keys("oriflux:session:*")
        ttl = await redis.ttl(keys[0])
        assert 0 < ttl <= SESSION_GAP_S

    async def test_concurrent_first_events_agree_on_one_session(self) -> None:
        tracker = SessionTracker(FakeAsyncRedis())
        ids = await asyncio.gather(*(tracker.session_for("visitor-a") for _ in range(10)))
        assert len(set(ids)) == 1


class TestSessionIdentity:
    """identify() binds the CURRENT session to a pseudonymous user id, server
    side (issue #17): subsequent events in the session carry user_pseudo_id
    with zero client-side storage."""

    async def test_identify_binds_the_session_to_the_user(self) -> None:
        tracker = SessionTracker(FakeAsyncRedis())
        session = await tracker.session_for("visitor-a")
        await tracker.identify(session, "usr_42")
        assert await tracker.user_for(session) == "usr_42"

    async def test_unidentified_session_has_no_user(self) -> None:
        tracker = SessionTracker(FakeAsyncRedis())
        session = await tracker.session_for("visitor-a")
        assert await tracker.user_for(session) == ""

    async def test_identity_does_not_leak_across_sessions(self) -> None:
        tracker = SessionTracker(FakeAsyncRedis())
        session_a = await tracker.session_for("visitor-a")
        session_b = await tracker.session_for("visitor-b")
        await tracker.identify(session_a, "usr_42")
        assert await tracker.user_for(session_b) == ""

    async def test_identity_expires_with_the_session_gap(self) -> None:
        redis = FakeAsyncRedis()
        tracker = SessionTracker(redis)
        session = await tracker.session_for("visitor-a")
        await tracker.identify(session, "usr_42")
        ttl = await redis.ttl(f"oriflux:session-user:{session}")
        assert 0 < ttl <= SESSION_GAP_S
