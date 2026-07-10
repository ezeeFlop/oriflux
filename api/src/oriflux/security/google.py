"""Google OAuth id_token verification boundary (ClipHaven pattern).

Kept behind one function so the API layer can be tested with a fake
verifier — the google-auth network call never runs in tests.
"""

from typing import Protocol

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel


class GoogleIdentity(BaseModel):
    sub: str
    email: str
    name: str = ""


class GoogleVerifier(Protocol):
    def __call__(self, token: str) -> GoogleIdentity: ...


class GoogleVerificationError(Exception):
    pass


def make_google_verifier(client_id: str) -> GoogleVerifier:
    def verify(token: str) -> GoogleIdentity:
        try:
            claims = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
                token, google_requests.Request(), client_id
            )
            # Unverified emails must never match an account: a pre-provisioned
            # member (added by email) could otherwise be taken over by anyone
            # who registers that address at Google without proving ownership.
            if claims.get("email_verified") is not True:
                raise GoogleVerificationError("email not verified by Google")
            return GoogleIdentity(
                sub=claims["sub"], email=claims["email"], name=claims.get("name", "")
            )
        except GoogleVerificationError:
            raise
        except Exception as exc:  # invalid token, transport failure, bad claims
            raise GoogleVerificationError(str(exc)) from exc

    return verify
