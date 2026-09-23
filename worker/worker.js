/**
 * 湛诺财务系统 —— AI 中转服务（Cloudflare Worker）
 *
 * 作用：客户的软件带着「授权码」来请求，本 Worker 校验授权码后，
 *      用你自己的大模型 API Key 转发请求。客户永远拿不到 Key。
 *
 * 需要在 Cloudflare 配置的 Secret（wrangler secret put）：
 *   LICENSE_SECRET   授权码签名密钥（新的，绝不能进代码仓库）
 *   AI_API_KEY       你的 DeepSeek / MiniMax API Key
 * 可选变量（wrangler.toml 的 [vars]）：
 *   AI_PROVIDER      deepseek（默认）| minimax
 *   AI_MODEL         deepseek-chat（默认）
 *   BLOCKED_CODES    被滥用的授权码，逗号分隔，例：ZN-20261231-AAAA1111,ZN-...
 *   MINIMAX_GROUP_ID 仅 provider=minimax 时需要
 */

const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: JSON_HEADERS });
}

/** HMAC-SHA256('ZN-YYYYMMDD' 或 'ZN-YYYYMMDD-SERIAL')，取前 8 位十六进制大写
 *  —— 与 Python 端算法一致 */
async function sign(payload, secret) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return [...new Uint8Array(sig)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 8)
    .toUpperCase();
}

/** 时间安全比较，避免时序侧信道 */
function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** 今天（UTC+8，按北京时间判断到期，对客户更直观） */
function todayCST() {
  const now = new Date(Date.now() + 8 * 3600 * 1000);
  return now.toISOString().slice(0, 10);
}

async function validateLicense(rawKey, env) {
  const key = (rawKey || "").trim().toUpperCase();
  if (!key) return { valid: false, expires: "", message: "未设置 AI 授权码" };

  const blocked = (env.BLOCKED_CODES || "")
    .split(",").map((x) => x.trim().toUpperCase()).filter(Boolean);
  if (blocked.includes(key)) {
    return { valid: false, expires: "", message: "该授权码已被停用，请联系卖家" };
  }

  // 新格式 ZN-YYYYMMDD-SERIAL-CHECKSUM（每客户唯一）
  // 旧格式 ZN-YYYYMMDD-CHECKSUM（兼容早期已发出的码）
  let d8, serial = null, checksum;
  let m = key.match(/^ZN-(\d{8})-([0-9A-Z]{4})-([A-F0-9]{8})$/);
  if (m) {
    [, d8, serial, checksum] = m;
  } else {
    m = key.match(/^ZN-(\d{8})-([A-F0-9]{8})$/);
    if (!m) return { valid: false, expires: "", message: "授权码格式不正确" };
    [, d8, checksum] = m;
  }

  const payload = serial ? `ZN-${d8}-${serial}` : `ZN-${d8}`;
  const expect = await sign(payload, env.LICENSE_SECRET);
  if (!timingSafeEqual(checksum, expect)) {
    return { valid: false, expires: "", message: "授权码无效（验证失败）" };
  }

  const expires = `${d8.slice(0, 4)}-${d8.slice(4, 6)}-${d8.slice(6, 8)}`;
  if (isNaN(new Date(expires).getTime())) {
    return { valid: false, expires: "", message: "授权码日期无效" };
  }
  if (todayCST() > expires) {
    return { valid: false, expires, message: `授权码已过期（${expires}）` };
  }
  return { valid: true, expires, message: `AI 授权有效，到期：${expires}` };
}

/** 转发到大模型 */
async function callModel(messages, maxTokens, env) {
  const provider = (env.AI_PROVIDER || "deepseek").toLowerCase();

  if (provider === "minimax") {
    const url = new URL("https://api.minimax.chat/v1/text/chatcompletion_v2");
    if (env.MINIMAX_GROUP_ID) url.searchParams.set("GroupId", env.MINIMAX_GROUP_ID);
    const r = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${env.AI_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: env.AI_MODEL || "abab6.5s-chat",
        messages, tokens_to_generate: maxTokens, temperature: 0.1,
      }),
    });
    if (!r.ok) throw new Error(`上游返回 ${r.status}: ${(await r.text()).slice(0, 200)}`);
    const d = await r.json();
    const c = d?.choices?.[0];
    if (!c) throw new Error("AI 返回空响应");
    return c.message?.content ?? c.messages?.at(-1)?.content ?? "";
  }

  const r = await fetch("https://api.deepseek.com/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.AI_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: env.AI_MODEL || "deepseek-chat",
      messages, max_tokens: maxTokens, temperature: 0.1,
    }),
  });
  if (!r.ok) throw new Error(`上游返回 ${r.status}: ${(await r.text()).slice(0, 200)}`);
  const d = await r.json();
  const content = d?.choices?.[0]?.message?.content;
  if (content == null) throw new Error("AI 返回空响应");
  return content;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: JSON_HEADERS });

    const { pathname } = new URL(request.url);

    if (pathname === "/" || pathname === "/health") {
      return json({ ok: true, service: "zhanno-ai-proxy" });
    }

    if (request.method !== "POST") return json({ detail: "只支持 POST" }, 405);

    if (!env.LICENSE_SECRET || !env.AI_API_KEY) {
      return json({ detail: "服务端未配置完成，请联系卖家" }, 500);
    }

    let body;
    try { body = await request.json(); }
    catch { return json({ detail: "请求格式错误" }, 400); }

    // ── 只校验授权码，不消耗 token —— 客户点「激活」时调用 ──
    if (pathname === "/v1/verify") {
      return json(await validateLicense(body.license, env));
    }

    // ── 校验授权码后转发给大模型 ──
    if (pathname === "/v1/chat") {
      const lic = await validateLicense(body.license, env);
      if (!lic.valid) return json({ detail: `AI 功能未授权：${lic.message}` }, 403);

      const messages = body.messages;
      if (!Array.isArray(messages) || messages.length === 0) {
        return json({ detail: "messages 不能为空" }, 400);
      }
      // 防止有人拿你的 Worker 当免费大模型代理
      const totalChars = JSON.stringify(messages).length;
      if (messages.length > 20 || totalChars > 20000) {
        return json({ detail: "请求内容过长" }, 413);
      }
      const maxTokens = Math.min(Math.max(parseInt(body.max_tokens) || 512, 1), 2048);

      try {
        const content = await callModel(messages, maxTokens, env);
        return json({ content, expires: lic.expires });
      } catch (e) {
        return json({ detail: `AI 调用失败：${e.message}` }, 502);
      }
    }

    return json({ detail: "未知接口" }, 404);
  },
};
