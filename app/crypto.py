import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _build_fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


fernet = _build_fernet()


def encrypt_message(content: str) -> str:
    return fernet.encrypt(content.encode("utf-8")).decode("utf-8")


def decrypt_message(content: str) -> str:
    try:
        return fernet.decrypt(content.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return content


def encrypt_bytes(content: bytes) -> bytes:
    return fernet.encrypt(content)


def decrypt_bytes(content: bytes) -> bytes:
    return fernet.decrypt(content)
