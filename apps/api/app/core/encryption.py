import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

# AES-256-GCM constants
_NONCE_BYTES = 12
_TAG_BYTES = 16


def _get_key() -> bytes:
    raw = get_settings().app_encryption_key
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError(f"app_encryption_key must decode to 32 bytes, got {len(key)}")
    return key


def encrypt(plaintext: str) -> bytes:
    """AES-256-GCM encrypt.

    Returns nonce (12 B) || ciphertext+tag stored as a single bytes blob.
    Each call produces a unique nonce so encrypting the same value twice
    yields different ciphertext — safe for storage.
    """
    nonce = os.urandom(_NONCE_BYTES)
    aesgcm = AESGCM(_get_key())
    # AESGCM.encrypt returns ciphertext || tag (tag appended automatically)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return nonce + ciphertext_with_tag


def decrypt(blob: bytes) -> str:
    """AES-256-GCM decrypt.

    Expects the blob format produced by encrypt(): nonce || ciphertext+tag.
    Raises cryptography.exceptions.InvalidTag on tampering or wrong key.
    """
    nonce = blob[:_NONCE_BYTES]
    ciphertext_with_tag = blob[_NONCE_BYTES:]
    aesgcm = AESGCM(_get_key())
    plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    return plaintext.decode()
