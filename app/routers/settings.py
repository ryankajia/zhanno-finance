import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import require_admin
from app.models import User
from app import config
from app.utils.app_paths import get_data_dir

router = APIRouter()
_SETTINGS_FILE = get_data_dir() / "ai_settings.json"


def read_settings() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_settings(data: dict):
    _SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class AIConfig(BaseModel):
    provider: str = "minimax"
    api_key: str = ""
    group_id: str = ""


@router.get("/ai")
def get_ai_config(_: User = Depends(require_admin)):
    s = read_settings()
    key = s.get("api_key", "")
    has_key = bool(key) or bool(config.MINIMAX_API_KEY)
    preview = ""
    if key:
        preview = key[:4] + "****"
    elif config.MINIMAX_API_KEY:
        preview = "本机 .env（开发用）"
    return {
        "provider": s.get("provider", "minimax"),
        "api_key_set": has_key,
        "api_key_preview": preview,
        "group_id": s.get("group_id", ""),
    }


@router.put("/ai")
def update_ai_config(body: AIConfig, _: User = Depends(require_admin)):
    s = read_settings()
    s["provider"] = body.provider
    if body.api_key.strip():
        s["api_key"] = body.api_key.strip()
    s["group_id"] = body.group_id.strip()
    write_settings(s)
    return {"ok": True}


@router.delete("/ai/key")
def clear_ai_key(_: User = Depends(require_admin)):
    s = read_settings()
    s.pop("api_key", None)
    write_settings(s)
    return {"ok": True}


@router.post("/ai/test")
async def test_ai_connection(_: User = Depends(require_admin)):
    """连通性自测：实际发一条最短的请求，验证授权码 + 网络 + 上游都正常。"""
    from app.utils.minimax import chat_completion
    try:
        result = await chat_completion(
            [{"role": "user", "content": "回复数字1"}],
            max_tokens=10,
        )
        return {"ok": True, "response": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── AI 授权码 ────────────────────────────────────────────────

class LicenseBody(BaseModel):
    key: str


@router.get("/license")
def get_license_status(_: User = Depends(require_admin)):
    """本地缓存的授权状态（真伪以中转服务为准）。"""
    from app.utils.license import local_status
    s = read_settings()
    key = s.get("license_key", "")
    preview = (key[:6] + "****") if key else ""
    return {"key_preview": preview, **local_status(s)}


@router.post("/license")
async def set_license_key(body: LicenseBody, _: User = Depends(require_admin)):
    """激活授权码：请求中转服务校验，通过后保存到期日。"""
    from app.utils.license import parse_format
    from app.utils.minimax import verify_license_remote

    key = body.key.strip().upper()
    ok, _expires = parse_format(key)
    if not ok:
        raise HTTPException(status_code=400, detail="授权码格式不正确")

    s = read_settings()
    try:
        result = await verify_license_remote(key, s)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"无法连接授权服务器：{e}")

    if not result.get("valid"):
        raise HTTPException(status_code=400, detail=result.get("message", "授权码无效"))

    s["license_key"] = key
    s["license_expires"] = result.get("expires", "")
    s["license_verified"] = True
    s.setdefault("provider", "zhanno")
    write_settings(s)
    return {"ok": True, **result}


@router.delete("/license")
def clear_license_key(_: User = Depends(require_admin)):
    s = read_settings()
    for k in ("license_key", "license_expires", "license_verified"):
        s.pop(k, None)
    write_settings(s)
    return {"ok": True}


@router.get("/self-check")
def self_check(_: User = Depends(require_admin)):
    """环境自检：中文 PDF 字体、数据目录、AI 授权与服务地址。客户报障时先看这里。"""
    import sys
    from app.utils.pdf_gen import font_status
    from app.utils.license import local_status
    from app.utils.minimax import worker_url

    data_dir = get_data_dir()
    s = read_settings()
    return {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "data_dir": str(data_dir),
        "db_exists": (data_dir / "zhanno_finance.db").exists(),
        "pdf_font": font_status(),
        "ai_provider": s.get("provider", "zhanno"),
        "ai_service_url": worker_url(s),
        "ai_license": local_status(s),
        "client_holds_api_key": bool(s.get("api_key")),
    }
