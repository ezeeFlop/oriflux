"""Dashboard JWTs (ClipHaven pattern: jose, HS256, short-lived access token)."""

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from oriflux.config import Settings


class InvalidToken(Exception):
    pass


def create_access_token(
    user_id: uuid.UUID, settings: Settings, *, expires_in: timedelta | None = None
) -> str:
    now = datetime.now(tz=UTC)
    expires = now + (expires_in or timedelta(minutes=settings.jwt_expire_minutes))
    claims = {"sub": str(user_id), "iat": now, "exp": expires}
    token: str = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return uuid.UUID(claims["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise InvalidToken(str(exc)) from exc
