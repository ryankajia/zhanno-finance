"""湛诺财务系统 AI 授权码（客户端）。

安全说明：
  授权码的签名密钥**只存在于 Cloudflare Worker**，不在本程序里，
  也不在代码仓库里。客户端只做格式检查和「上次校验结果」的本地缓存，
  真正的有效性判定由 Worker 在每次 AI 调用时完成——
  因此即使有人反编译本程序，也无法伪造授权码。
"""
import re
from datetime import date, datetime

_FORMAT = re.compile(r"^ZN-(\d{8})-([A-F0-9]{8})$")


def parse_format(key: str) -> tuple[bool, str]:
    """只检查格式，返回 (格式是否正确, 到期日字符串)。不判定真伪。"""
    key = (key or "").strip().upper()
    m = _FORMAT.match(key)
    if not m:
        return False, ""
    d8 = m.group(1)
    try:
        expires = datetime.strptime(d8, "%Y%m%d").date()
    except ValueError:
        return False, ""
    return True, expires.isoformat()


def local_status(settings: dict) -> dict:
    """根据本地缓存判断授权状态（用于界面显示和快速拦截）。

    真伪以 Worker 为准；这里只是避免明显无效时还去发无谓的网络请求。
    """
    key = (settings.get("license_key") or "").strip().upper()
    if not key:
        return {"valid": False, "expires": "", "message": "未设置 AI 授权码"}

    ok, expires = parse_format(key)
    if not ok:
        return {"valid": False, "expires": "", "message": "授权码格式不正确"}

    # 以服务器确认过的到期日为准，没有则退回授权码里写的日期
    expires = settings.get("license_expires") or expires

    if date.today().isoformat() > expires:
        return {"valid": False, "expires": expires, "message": f"授权码已过期（{expires}）"}

    if not settings.get("license_verified"):
        return {"valid": False, "expires": expires,
                "message": "授权码尚未激活，请在「系统设置」中点击激活"}

    return {"valid": True, "expires": expires, "message": f"AI 授权有效，到期：{expires}"}
