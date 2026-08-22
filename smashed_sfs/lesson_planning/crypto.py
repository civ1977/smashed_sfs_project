from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = settings.AI_KEY_ENCRYPTION_KEY
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_api_key(raw_key):
    return _fernet().encrypt(raw_key.encode()).decode()


def decrypt_api_key(encrypted_key):
    """Raises InvalidToken if AI_KEY_ENCRYPTION_KEY has changed since this
    row was encrypted (e.g. after a key rotation) - callers should treat
    that the same as "no connection" and prompt the teacher to reconnect,
    rather than crash."""
    return _fernet().decrypt(encrypted_key.encode()).decode()
