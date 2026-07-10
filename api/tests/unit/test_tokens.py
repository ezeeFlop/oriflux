"""Seam: dashboard JWTs (ClipHaven pattern — jose, HS256)."""

import uuid
from datetime import timedelta

import pytest

from oriflux.config import Settings
from oriflux.security.tokens import InvalidToken, create_access_token, decode_access_token

SETTINGS = Settings(jwt_secret="test-secret")


class TestJwtRoundtrip:
    def test_roundtrip_returns_the_user_id(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(user_id, SETTINGS)
        assert decode_access_token(token, SETTINGS) == user_id

    def test_expired_token_is_rejected(self) -> None:
        token = create_access_token(uuid.uuid4(), SETTINGS, expires_in=timedelta(seconds=-1))
        with pytest.raises(InvalidToken):
            decode_access_token(token, SETTINGS)

    def test_garbage_is_rejected(self) -> None:
        with pytest.raises(InvalidToken):
            decode_access_token("not-a-jwt", SETTINGS)

    def test_wrong_secret_is_rejected(self) -> None:
        token = create_access_token(uuid.uuid4(), SETTINGS)
        with pytest.raises(InvalidToken):
            decode_access_token(token, Settings(jwt_secret="other-secret"))
