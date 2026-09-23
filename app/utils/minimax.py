"""AI 调用层。

默认走「湛诺官方 AI 服务」——即部署在 Cloudflare 上的中转 Worker：
客户端只发送授权码和问题，Worker 校验授权码后用卖家自己的
大模型 Key 转发。**客户端不持有任何大模型 API Key。**

provider 取值：
  zhanno    （默认）经由中转服务，客户只需授权码
  deepseek  直连 DeepSeek，需自备 API Key（开发/自用）
  minimax   直连 MiniMax，需自备 API Key（开发/自用）
"""
import json
import os
import httpx
from app import config
from app.utils.app_paths import get_data_dir

# 中转服务地址。部署后如域名不同，可在 ai_settings.json 里用 worker_url 覆盖，
# 或设置环境变量 ZHANNO_AI_URL。
DEFAULT_WORKER_URL = "https://zhanno-ai.ryankajia.workers.dev"

_BASE_MINIMAX = "https://api.minimax.chat/v1/text/chatcompletion_v2"
_BASE_DEEPSEEK = "https://api.deepseek.com/chat/completions"
_SETTINGS_FILE = get_data_dir() / "ai_settings.json"


def load_ai_config() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def worker_url(s: dict | None = None) -> str:
    s = s if s is not None else load_ai_config()
    return (s.get("worker_url") or os.getenv("ZHANNO_AI_URL") or DEFAULT_WORKER_URL).rstrip("/")


async def verify_license_remote(license_key: str, s: dict | None = None) -> dict:
    """请求中转服务校验授权码（不消耗 token）。"""
    url = f"{worker_url(s)}/v1/verify"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json={"license": license_key})
    if resp.status_code >= 500:
        raise ValueError("授权服务器暂时不可用，请稍后重试")
    return resp.json()


async def chat_completion(messages: list, max_tokens: int = 1024) -> str:
    s = load_ai_config()
    provider = s.get("provider", "zhanno")

    if provider == "zhanno":
        return await _via_proxy(messages, max_tokens, s)

    api_key = s.get("api_key") or (config.MINIMAX_API_KEY if provider == "minimax" else None)
    if not api_key:
        raise ValueError("AI API Key 未配置，请在「系统设置」页面填写")
    if provider == "deepseek":
        return await _deepseek(messages, api_key, max_tokens)
    return await _minimax(messages, api_key, s.get("group_id") or config.MINIMAX_GROUP_ID, max_tokens)


async def _via_proxy(messages: list, max_tokens: int, s: dict) -> str:
    license_key = (s.get("license_key") or "").strip().upper()
    if not license_key:
        raise ValueError("未设置 AI 授权码，请在「系统设置 → AI 功能授权」中激活")

    url = f"{worker_url(s)}/v1/chat"
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(url, json={
                "license": license_key,
                "messages": messages,
                "max_tokens": max_tokens,
            })
    except httpx.RequestError:
        raise ValueError("无法连接 AI 服务，请检查网络连接后重试")

    if resp.status_code == 403:
        raise ValueError(resp.json().get("detail", "AI 功能未授权"))
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        raise ValueError(detail)

    data = resp.json()
    content = data.get("content")
    if not content:
        raise ValueError("AI 返回空响应")
    return content


async def _minimax(messages: list, api_key: str, group_id: str | None, max_tokens: int) -> str:
    params = {"GroupId": group_id} if group_id else {}
    payload = {"model": "abab6.5s-chat", "messages": messages,
               "tokens_to_generate": max_tokens, "temperature": 0.1}
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
    payload = {"model": "deepseek-chat", "messages": messages,
               "max_tokens": max_tokens, "temperature": 0.1}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_BASE_DEEPSEEK, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ValueError("AI 返回空响应")
    return choices[0]["message"]["content"]
