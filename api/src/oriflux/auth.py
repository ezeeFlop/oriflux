"""Bearer-key auth shared by the ingest and api services.

Walking-skeleton scope: each service checks one hardcoded key from settings.
Real scoped API keys in PostgreSQL arrive with issue #3.
"""

import secrets
from collections.abc import Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def require_bearer_key(expected_key: str) -> Callable[..., None]:
    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> None:
        if credentials is None or not secrets.compare_digest(
            credentials.credentials, expected_key
        ):
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    return dependency
