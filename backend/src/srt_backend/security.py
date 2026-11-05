"""R10: OAuth tokens encrypted at rest with keys in a KMS; app sessions as signed JWTs.

Production: envelope encryption - a fresh data key per token, wrapped by Cloud KMS
(KMS_KEY_NAME, India region). Development/tests: a local Fernet key (LOCAL_TOKEN_KEY),
which does NOT satisfy R10 and is refused when REGION is a production region and
ENV=production.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
from typing import Protocol

import jwt
from cryptography.fernet import Fernet

from .config import settings


class TokenCipher(Protocol):
    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, ciphertext: bytes) -> bytes: ...


class LocalCipher:
    def __init__(self, key: str | None = None) -> None:
        key = key or settings().local_token_key or Fernet.generate_key().decode()
        self._f = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._f.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._f.decrypt(ciphertext)


class KmsEnvelopeCipher:
    """Data key per token (Fernet), wrapped with Cloud KMS. Stored as JSON {k: wrapped, c: ciphertext}."""

    def __init__(self, key_name: str) -> None:
        from google.cloud import kms  # optional dependency: pip install srt-backend[gcp]

        self._client = kms.KeyManagementServiceClient()
        self._key = key_name

    def encrypt(self, plaintext: bytes) -> bytes:
        dek = Fernet.generate_key()
        wrapped = self._client.encrypt(request={"name": self._key, "plaintext": dek}).ciphertext
        return json.dumps({"k": base64.b64encode(wrapped).decode(), "c": Fernet(dek).encrypt(plaintext).decode()}).encode()

    def decrypt(self, ciphertext: bytes) -> bytes:
        d = json.loads(ciphertext)
        dek = self._client.decrypt(request={"name": self._key, "ciphertext": base64.b64decode(d["k"])}).plaintext
        return Fernet(dek).decrypt(d["c"].encode())


_cipher: TokenCipher | None = None


def cipher() -> TokenCipher:
    global _cipher
    if _cipher is None:
        s = settings()
        if s.kms_key_name:
            _cipher = KmsEnvelopeCipher(s.kms_key_name)
        else:
            if os.environ.get("ENV") == "production":
                raise RuntimeError("KMS_KEY_NAME is required in production (R10)")
            _cipher = LocalCipher()
    return _cipher


def set_cipher(c: TokenCipher | None) -> None:
    global _cipher
    _cipher = c


def issue_session(user_id: int) -> str:
    s = settings()
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + dt.timedelta(days=s.jwt_ttl_days)},
                      s.jwt_secret, algorithm="HS256")


def verify_session(token: str) -> int:
    return int(jwt.decode(token, settings().jwt_secret, algorithms=["HS256"])["sub"])
