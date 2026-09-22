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
    from app.utils.license import validate_license
    s = read_settings()
    key = s.get("license_key", "")
    result = validate_license(key)
    preview = (key[:6] + "****") if key else ""
    return {"key_preview": preview, **result}


@router.post("/license")
def set_license_key(body: LicenseBody, _: User = Depends(require_admin)):
    from app.utils.license import validate_license
    key = body.key.strip().upper()
    result = validate_license(key)
    if not result["valid"]:
        raise HTTPException(status_code=400, detail=result["message"])
    s = read_settings()
    s["license_key"] = key
    write_settings(s)
    return {"ok": True, **result}


@router.delete("/license")
def clear_license_key(_: User = Depends(require_admin)):
    s = read_settings()
    s.pop("license_key", None)
    write_settings(s)
    return {"ok": True}


@router.get("/self-check")
def self_check(_: User = Depends(require_admin)):
    """环境自检：中文 PDF 字体、数据目录、AI 配置。客户报障时先看这里。"""
    import sys
    from app.utils.pdf_gen import font_status
    from app.utils.license import validate_license

    data_dir = get_data_dir()
    s = read_settings()
    fonts = font_status()
    return {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "data_dir": str(data_dir),
        "db_exists": (data_dir / "zhanno_finance.db").exists(),
        "pdf_font": fonts,
        "ai_key_configured": bool(s.get("api_key") or config.MINIMAX_API_KEY),
        "ai_license": validate_license(s.get("license_key", "")),
    }
