"""Fernet encryption for connector secrets at rest (PRD §9, issue #24)."""

from cryptography.fernet import Fernet


def generate_fernet_key() -> str:
    return Fernet.generate_key().decode()


def encrypt_secret(plaintext: str, key: str) -> str:
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str, key: str) -> str:
    return Fernet(key.encode()).decrypt(token.encode()).decode()
