from __future__ import annotations

import base64
import hashlib
import os
import sys

from cryptography.fernet import Fernet, InvalidToken


class SecretVault:
    PREFIX = "fernet:"

    def __init__(self, key: str | None):
        self._raw_key = key.strip() if key else ""
        self._fernet = Fernet(self._normalize_key(self._raw_key)) if self._raw_key else None

    @staticmethod
    def _normalize_key(value: str) -> bytes:
        raw = value.encode("utf-8")
        try:
            Fernet(raw)
            return raw
        except (ValueError, TypeError):
            return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())

    @classmethod
    def from_env(cls) -> "SecretVault":
        return cls(os.getenv("ROUTER_VAULT_KEY"))

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def encrypt(self, value: str) -> str:
        if not self._fernet:
            return value
        token = self._fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return self.PREFIX + token

    def decrypt(self, value: str) -> str | None:
        if not value.startswith(self.PREFIX):
            return value
        if not self._fernet:
            return None
        token = value[len(self.PREFIX) :].encode("ascii")
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except (InvalidToken, ValueError):
            return None

    def is_encrypted(self, value: str) -> bool:
        return value.startswith(self.PREFIX)


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "generate-key":
        print(generate_key())
    else:
        print("Usage: python -m app.vault generate-key")
        raise SystemExit(2)
