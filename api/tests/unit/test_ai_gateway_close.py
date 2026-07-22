"""Seam: AiGateway owns and closes its httpx client.

Root cause of the recurring prod worker FD exhaustion (Errno 24, ~1000 dead
socket FDs): the scheduled jobs build `AiGateway(settings, factory)` per run
(evaluate_alerts every 60 s, plus the hourly/daily jobs) and never closed it.
Each AI HTTPS call's keep-alive connection socket then leaks. A gateway that
created its own httpx client must close it; a gateway handed an external
client must leave it to the caller.
"""

from unittest.mock import MagicMock

import httpx

from oriflux.ai.gateway import AiGateway
from oriflux.config import Settings


async def test_aclose_closes_the_client_it_created() -> None:
    gw = AiGateway(Settings(spt_models_url="https://models.test"), MagicMock())
    assert gw._client is not None and not gw._client.is_closed

    await gw.aclose()

    assert gw._client.is_closed


async def test_aclose_leaves_an_injected_client_open() -> None:
    injected = httpx.AsyncClient()
    gw = AiGateway(
        Settings(spt_models_url="https://models.test"), MagicMock(), client=injected
    )

    await gw.aclose()

    assert not injected.is_closed  # not owned → caller still owns it
    await injected.aclose()
