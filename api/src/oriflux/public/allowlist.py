"""Public-dashboard allow-list (issue #41).

A public share may only run a curated, safe subset — enforced SERVER-SIDE
(never UI hiding): no revenue, no API internals, no live view. Any query
outside this list is rejected before it reaches the engine.
"""

from oriflux.query.models import QueryRequest

PUBLIC_METRICS: frozenset[str] = frozenset({
    "visitors", "pageviews", "sessions", "bounce_rate", "session_duration",
})
PUBLIC_DIMENSIONS: frozenset[str] = frozenset({
    "country", "region", "city", "page", "referrer",
    "utm_source", "utm_medium", "utm_campaign", "device", "os", "browser",
})


def is_public_query(request: QueryRequest) -> bool:
    if request.metric not in PUBLIC_METRICS:
        return False
    if any(dim not in PUBLIC_DIMENSIONS for dim in request.dimensions):
        return False
    return all(f.dimension in PUBLIC_DIMENSIONS for f in request.filters)
