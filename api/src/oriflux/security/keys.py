"""API key material: generation and at-rest hashing.

Plaintext keys are returned once at issuance; only the sha256 hash is
persisted (`api_keys.key_hash`), so a database leak reveals no usable keys.
sha256 (not bcrypt) is deliberate: keys are 32 bytes of entropy, not
passwords, and ingest validates one hash per request on the hot path.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass

from oriflux.db.models import ApiKey, KeyScope

_PREFIXES = {KeyScope.ingest: "ofx_ing_", KeyScope.read: "ofx_read_"}


@dataclass(frozen=True)
class IssuedKey:
    plaintext: str
    key_hash: str
    key_prefix: str


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def generate_api_key(scope: KeyScope) -> IssuedKey:
    plaintext = f"{_PREFIXES[scope]}{secrets.token_urlsafe(32)}"
    return IssuedKey(
        plaintext=plaintext,
        key_hash=hash_api_key(plaintext),
        key_prefix=plaintext[:12],
    )


def build_api_key(
    *,
    org_id: uuid.UUID,
    scope: KeyScope,
    source_id: uuid.UUID | None = None,
    name: str = "",
) -> tuple[ApiKey, str]:
    """One issuance path for admin endpoints and bootstrap: returns the row
    to persist and the plaintext to show exactly once."""
    issued = generate_api_key(scope)
    row = ApiKey(
        org_id=org_id,
        source_id=source_id,
        scope=scope,
        key_hash=issued.key_hash,
        key_prefix=issued.key_prefix,
        name=name,
    )
    return row, issued.plaintext
