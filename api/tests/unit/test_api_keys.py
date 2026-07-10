"""Seam: API key material — generation, at-rest hashing, scope tagging.

Plaintext keys are shown once at issuance and never stored; only the sha256
hash is persisted. The prefix makes a key's scope recognizable in logs and
UIs without revealing the secret.
"""

from oriflux.db.models import KeyScope
from oriflux.security.keys import generate_api_key, hash_api_key


class TestKeyGeneration:
    def test_generated_keys_are_unique(self) -> None:
        a = generate_api_key(KeyScope.ingest)
        b = generate_api_key(KeyScope.ingest)
        assert a.plaintext != b.plaintext
        assert a.key_hash != b.key_hash

    def test_scope_is_recognizable_from_the_prefix(self) -> None:
        assert generate_api_key(KeyScope.ingest).plaintext.startswith("ofx_ing_")
        assert generate_api_key(KeyScope.read).plaintext.startswith("ofx_read_")

    def test_only_the_hash_is_meant_for_storage(self) -> None:
        issued = generate_api_key(KeyScope.read)
        assert issued.key_hash == hash_api_key(issued.plaintext)
        assert len(issued.key_hash) == 64  # sha256 hex
        assert issued.plaintext not in issued.key_hash

    def test_display_prefix_is_a_safe_truncation(self) -> None:
        issued = generate_api_key(KeyScope.ingest)
        assert issued.key_prefix == issued.plaintext[:12]

    def test_hashing_is_deterministic(self) -> None:
        assert hash_api_key("ofx_ing_x") == hash_api_key("ofx_ing_x")
