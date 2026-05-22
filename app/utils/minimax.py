import json
import httpx
from pathlib import Path
from app import config
from app.utils.app_paths import get_data_dir

_BASE_MINIMAX = "https://api.minimax.chat/v1/text/chatcompletion_v2"
_BASE_DEEPSEEK = "https://api.deepseek.com/chat/completions"
_SETTINGS_FILE = get_data_dir() / "ai_settings.json"


def _load_ai_config() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


async def chat_completion(messages: list, max_tokens: int = 1024) -> str:
    s = _load_ai_config()
    provider = s.get("provider", "minimax")
    api_key = s.get("api_key") or (config.MINIMAX_API_KEY if provider == "minimax" else None)
    group_id = s.get("group_id") or config.MINIMAX_GROUP_ID

    if not api_key:
        raise ValueError("AI API Key 未配置，请在「系统设置」页面填写")

    if provider == "deepseek":
        return await _deepseek(messages, api_key, max_tokens)
    return await _minimax(messages, api_key, group_id, max_tokens)


async def _minimax(messages: list, api_key: str, group_id: str | None, max_tokens: int) -> str:
    params = {}
    if group_id:
        params["GroupId"] = group_id
    payload = {
        "model": "abab6.5s-chat",
        "messages": messages,
        "tokens_to_generate": max_tokens,
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_BASE_MINIMAX, params=params, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ValueError("AI 返回空响应")
    choice = choices[0]
    if "message" in choice:
        return choice["message"]["content"]
    if "messages" in choice:
        return choice["messages"][-1]["content"]
    raise ValueError(f"未知响应格式: {choice}")


async def _deepseek(messages: list, api_key: str, max_tokens: int) -> str:
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_BASE_DEEPSEEK, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ValueError("AI 返回空响应")
    return choices[0]["message"]["content"]
