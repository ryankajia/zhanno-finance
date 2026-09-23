"""湛诺财务系统 —— AI 中转服务（部署在自己的服务器上）

与 Cloudflare Worker 逻辑完全一致，改为 Python 版，
部署在国内服务器上，解决 workers.dev 在大陆访问不稳的问题。

客户端携带授权码请求，本服务校验通过后用卖家自己的 MiniMax Key 转发。
客户端不持有任何大模型凭据。

配置从 /etc/zhanno-ai/config.env 读取（由 deploy.sh 生成）：
  LICENSE_SECRET    授权码签名密钥
  AI_API_KEY        MiniMax API Key
  MINIMAX_GROUP_ID  MiniMax GroupId
  AI_MODEL          默认 abab6.5s-chat
  BLOCKED_CODES     被停用的授权码，逗号分隔
"""
import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

_CST = timezone(timedelta(hours=8))          # 按北京时间判断到期，对客户更直观
_MINIMAX_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"

# 新格式 ZN-YYYYMMDD-SERIAL-CHECKSUM；旧格式 ZN-YYYYMMDD-CHECKSUM
_NEW = re.compile(r"^ZN-(\d{8})-([0-9A-Z]{4})-([A-F0-9]{8})$")
_OLD = re.compile(r"^ZN-(\d{8})-([A-F0-9]{8})$")

app = FastAPI(title="湛诺 AI 中转服务", docs_url=None, redoc_url=None, openapi_url=None)


def _cfg(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _sign(payload: str) -> str:
    secret = _cfg("LICENSE_SECRET").encode()
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:8].upper()


def _today() -> str:
    return datetime.now(_CST).date().isoformat()


def validate_license(raw: str) -> dict:
    key = (raw or "").strip().upper()
    if not key:
        return {"valid": False, "expires": "", "message": "未设置 AI 授权码"}

    blocked = {x.strip().upper() for x in _cfg("BLOCKED_CODES").split(",") if x.strip()}
    if key in blocked:
        return {"valid": False, "expires": "", "message": "该授权码已被停用，请联系卖家"}

    m = _NEW.match(key)
    if m:
        d8, serial, checksum = m.group(1), m.group(2), m.group(3)
        payload = f"ZN-{d8}-{serial}"
    else:
        m = _OLD.match(key)
        if not m:
            return {"valid": False, "expires": "", "message": "授权码格式不正确"}
        d8, checksum = m.group(1), m.group(2)
        payload = f"ZN-{d8}"

    if not hmac.compare_digest(checksum, _sign(payload)):
        return {"valid": False, "expires": "", "message": "授权码无效（验证失败）"}

    try:
        expire = datetime.strptime(d8, "%Y%m%d").date()
    except ValueError:
        return {"valid": False, "expires": "", "message": "授权码日期无效"}

    expires = expire.isoformat()
    if _today() > expires:
        return {"valid": False, "expires": expires, "message": f"授权码已过期（{expires}）"}
    return {"valid": True, "expires": expires, "message": f"AI 授权有效，到期：{expires}"}


async def call_model(messages: list, max_tokens: int) -> str:
    api_key = _cfg("AI_API_KEY")
    if not api_key:
        raise RuntimeError("服务端未配置 AI_API_KEY")

    params = {}
    gid = _cfg("MINIMAX_GROUP_ID")
    if gid:
        params["GroupId"] = gid

    payload = {
        "model": _cfg("AI_MODEL", "abab6.5s-chat"),
        "messages": messages,
        "tokens_to_generate": max_tokens,
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(_MINIMAX_URL, params=params, json=payload, headers=headers)
    if r.status_code != 200:
        raise RuntimeError(f"上游返回 {r.status_code}: {r.text[:200]}")

    data = r.json()
    base = data.get("base_resp") or {}
    if base.get("status_code"):
        raise RuntimeError(f"上游错误: {base.get('status_msg')}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("AI 返回空响应")
    c = choices[0]
    if "message" in c:
        return c["message"]["content"]
    if "messages" in c:
        return c["messages"][-1]["content"]
    raise RuntimeError("未知响应格式")


class VerifyBody(BaseModel):
    license: str = ""


class ChatBody(BaseModel):
    license: str = ""
    messages: list = []
    max_tokens: int = 512


@app.get("/health")
@app.get("/")
def health():
    return {"ok": True, "service": "zhanno-ai-proxy", "host": "tencent"}


@app.post("/v1/verify")
def verify(body: VerifyBody):
    if not _cfg("LICENSE_SECRET"):
        raise HTTPException(status_code=500, detail="服务端未配置完成，请联系卖家")
    return validate_license(body.license)


@app.post("/v1/chat")
async def chat(body: ChatBody):
    if not _cfg("LICENSE_SECRET") or not _cfg("AI_API_KEY"):
        raise HTTPException(status_code=500, detail="服务端未配置完成，请联系卖家")

    lic = validate_license(body.license)
    if not lic["valid"]:
        raise HTTPException(status_code=403, detail=f"AI 功能未授权：{lic['message']}")

    msgs = body.messages
    if not isinstance(msgs, list) or not msgs:
        raise HTTPException(status_code=400, detail="messages 不能为空")
    # 防止有人拿这个服务当免费大模型代理
    if len(msgs) > 20 or len(str(msgs)) > 20000:
        raise HTTPException(status_code=413, detail="请求内容过长")

    max_tokens = min(max(int(body.max_tokens or 512), 1), 2048)
    try:
        content = await call_model(msgs, max_tokens)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 调用失败：{e}")
    return {"content": content, "expires": lic["expires"]}


@app.exception_handler(HTTPException)
async def _http_exc(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
