"""湛诺财务系统 AI 功能授权码工具。"""
import hmac
import hashlib
import re
from datetime import date

_SECRET = b"zhanno-finance-license-2025-v1-ryankajia"


def _sign(ym6: str) -> str:
    """HMAC-SHA256('ZN-YYYYMM')，取前8位十六进制大写。"""
    msg = f"ZN-{ym6}".encode()
    return hmac.new(_SECRET, msg, hashlib.sha256).hexdigest()[:8].upper()


def generate_license(year_month: str) -> str:
    """year_month='2025-06' → 'ZN-202506-XXXXXXXX'"""
    ym6 = year_month.replace("-", "")
    return f"ZN-{ym6}-{_sign(ym6)}"


def validate_license(key: str) -> dict:
    """返回 {'valid': bool, 'expires': 'YYYY-MM', 'message': str}"""
    if not key or not key.strip():
        return {"valid": False, "expires": "", "message": "未设置 AI 授权码"}

    key = key.strip().upper()
    m = re.match(r"^ZN-(\d{6})-([A-F0-9]{8})$", key)
    if not m:
        return {"valid": False, "expires": "", "message": "授权码格式不正确"}

    ym6, checksum = m.group(1), m.group(2)
    if not hmac.compare_digest(checksum, _sign(ym6)):
        return {"valid": False, "expires": "", "message": "授权码无效（验证失败）"}

    year, month = int(ym6[:4]), int(ym6[4:])
    today = date.today()
    expires_str = f"{year}-{month:02d}"

    if today.year > year or (today.year == year and today.month > month):
        return {"valid": False, "expires": expires_str, "message": f"授权码已过期（{expires_str}）"}

    return {"valid": True, "expires": expires_str, "message": f"AI 授权有效，到期：{expires_str} 月底"}
