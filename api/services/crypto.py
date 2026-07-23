"""AES-256 encryption helpers for API key storage.

Uses the `cryptography` package's Fernet symmetric encryption.
The Fernet key is derived from the SECRET_KEY env var via PBKDF2-HMAC-SHA256.

Usage:
    from services.crypto import encrypt, decrypt

    token = encrypt("sk-abc123...")
    plaintext = decrypt(token)
"""
import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Salt is fixed per-deployment — the SECRET_KEY is the true secret.
# Using a fixed salt means the same SECRET_KEY always produces the same Fernet key,
# which lets us decrypt values stored before a container restart.
_SALT = b"rvtool-genesis-v1"


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the SECRET_KEY environment variable."""
    from core.config import settings  # import here to avoid circular import at module load

    secret = settings.secret_key.encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret))
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string and return a base64 Fernet token (str)."""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token back to plaintext.

    Raises ValueError if the token is invalid or was encrypted with a different key.
    """
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except (InvalidToken, Exception) as exc:
        raise ValueError(f"Failed to decrypt value — check SECRET_KEY: {exc}") from exc
