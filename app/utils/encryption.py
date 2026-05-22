from cryptography.fernet import Fernet, InvalidToken
from app import config

_fernet: Fernet | None = None


def _get_fernet() -> Fernet | None:
    global _fernet
    if _fernet is None and config.ENCRYPTION_KEY:
        _fernet = Fernet(config.ENCRYPTION_KEY.encode())
    return _fernet


def encrypt(text: str) -> str:
    f = _get_fernet()
    if not f or not text:
        return text
    return f.encrypt(text.encode()).decode()


def decrypt(text: str) -> str:
    f = _get_fernet()
    if not f or not text:
        return text
    try:
        return f.decrypt(text.encode()).decode()
    except (InvalidToken, Exception):
        return text  # 返回原文（首次迁移场景）
