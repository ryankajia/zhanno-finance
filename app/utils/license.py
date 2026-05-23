"""湛诺财务系统 AI 功能授权码工具。"""
import hmac
import hashlib
import re
from datetime import date, datetime

_SECRET = b"zhanno-finance-license-2025-v1-ryankajia"


def _sign(d8: str) -> str:
    """HMAC-SHA256('ZN-YYYYMMDD')，取前8位十六进制大写。"""
    msg = f"ZN-{d8}".encode()
    return hmac.new(_SECRET, msg, hashlib.sha256).hexdigest()[:8].upper()


def generate_license(expire_date: str) -> str:
    """expire_date='2026-07-04' → 'ZN-20260704-XXXXXXXX'"""
    d8 = expire_date.replace("-", "")
    if len(d8) != 8 or not d8.isdigit():
        raise ValueError(f"日期格式应为 YYYY-MM-DD，收到：{expire_date}")
    return f"ZN-{d8}-{_sign(d8)}"


def validate_license(key: str) -> dict:
    """返回 {'valid': bool, 'expires': 'YYYY-MM-DD', 'message': str}"""
    if not key or not key.strip():
        return {"valid": False, "expires": "", "message": "未设置 AI 授权码"}

    key = key.strip().upper()
    m = re.match(r"^ZN-(\d{8})-([A-F0-9]{8})$", key)
    if not m:
        return {"valid": False, "expires": "", "message": "授权码格式不正确"}

    d8, checksum = m.group(1), m.group(2)
    if not hmac.compare_digest(checksum, _sign(d8)):
        return {"valid": False, "expires": "", "message": "授权码无效（验证失败）"}

    try:
        expire = datetime.strptime(d8, "%Y%m%d").date()
    except ValueError:
        return {"valid": False, "expires": "", "message": "授权码日期无效"}

    expires_str = expire.strftime("%Y-%m-%d")
    if date.today() > expire:
        return {"valid": False, "expires": expires_str, "message": f"授权码已过期（{expires_str}）"}

    return {"valid": True, "expires": expires_str, "message": f"AI 授权有效，到期：{expires_str}"}
