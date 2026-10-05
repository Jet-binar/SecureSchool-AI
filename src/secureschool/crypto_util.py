"""Encrypt stored face embeddings. The key stays in the local data folder."""

from cryptography.fernet import Fernet

from . import config


def _fernet():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not config.FERNET_PATH.exists():
        config.FERNET_PATH.write_bytes(Fernet.generate_key())
    return Fernet(config.FERNET_PATH.read_bytes())


def encrypt_bytes(raw):
    return _fernet().encrypt(raw)


def decrypt_bytes(token):
    return _fernet().decrypt(token)
