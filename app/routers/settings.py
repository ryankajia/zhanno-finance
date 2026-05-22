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
        preview = "内置密钥"
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
