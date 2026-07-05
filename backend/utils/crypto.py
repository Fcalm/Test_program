"""API Key 加密/解密工具（Fernet 对称加密）"""

from cryptography.fernet import Fernet
from backend.config import settings


def _get_fernet() -> Fernet:
    """从 SECRET_KEY 派生 Fernet 实例"""
    import hashlib, base64
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_api_key(key: str) -> str:
    """加密 API Key"""
    if not key:
        return ""
    return _get_fernet().encrypt(key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    """解密 API Key"""
    if not encrypted:
        return ""
    return _get_fernet().decrypt(encrypted.encode()).decode()