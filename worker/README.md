# 湛诺 AI 中转服务 —— 部署说明

把你的大模型 API Key 放在 Cloudflare 上，客户只拿到「授权码」。
客户不续费 → 授权码过期 → Worker 拒绝转发 → AI 停用。**客户永远拿不到你的 Key。**

```
客户软件 ──(授权码 + 问题)──▶ Cloudflare Worker ──(你的 Key)──▶ DeepSeek
                                    │
                                    └─ 校验授权码签名 + 到期日，不通过直接拒绝
```

费用：Cloudflare Workers 免费额度 **10 万次请求/天**，正常经营用不满，**0 元**。

---

## 一次性部署（约 10 分钟）

### 1. 准备两个密钥

**① 授权码签名密钥** —— 项目根目录的 `.license_secret` 文件里已经自动生成好了：

```bash
cat ../.license_secret
```

⚠️ 这个文件已加入 `.gitignore`，**绝不能提交到 GitHub**。请另外备份一份到密码管理器，
丢了就无法再生成能被 Worker 认可的授权码。

**② 大模型 API Key** —— 去 https://platform.deepseek.com 注册并充值（几十元能用很久），
创建一个 API Key 备用。

### 2. 登录 Cloudflare 并部署

在 `worker/` 目录下执行：

```bash
npx wrangler login          # 浏览器里用 ryankajia@gmail.com 登录授权
npx wrangler deploy         # 首次部署
```

部署成功后会打印出地址，形如：

```
https://zhanno-ai.<你的子域>.workers.dev
```

**把这个地址记下来**，下一步要用。

### 3. 写入两个 Secret

```bash
npx wrangler secret put LICENSE_SECRET
# 粘贴 ../.license_secret 文件里的内容，回车

npx wrangler secret put AI_API_KEY
# 粘贴你的 DeepSeek API Key，回车
```

Secret 存在 Cloudflare 上，加密保存，**不会出现在代码、日志或客户端里**。

### 4. 确认客户端地址一致

打开 `app/utils/minimax.py`，把 `DEFAULT_WORKER_URL` 改成第 2 步拿到的真实地址：

```python
DEFAULT_WORKER_URL = "https://zhanno-ai.你的子域.workers.dev"
```

改完重新打包（`git push` 触发自动构建），新安装包就会指向你的服务。

### 5. 验证

```bash
curl https://zhanno-ai.<你的子域>.workers.dev/health
# 期望：{"ok":true,"service":"zhanno-ai-proxy"}

# 用一个真授权码测试
curl -X POST https://zhanno-ai.<你的子域>.workers.dev/v1/verify \
  -H 'Content-Type: application/json' \
  -d '{"license":"ZN-20261231-XXXXXXXX"}'
```

---

## 日常运营

### 客户付款后，发码给他

```bash
cd ..                                   # 回项目根目录
python generate_license.py --month      # 一个月后到期（最常用）
python generate_license.py --year       # 一年后到期
python generate_license.py 2026-12-31   # 指定到期日
```

把生成的码（形如 `ZN-20261231-A1B2C3D4`）发给客户，
让他在软件「系统设置 → AI 功能授权」中粘贴，点激活。**客户全程只需这一步。**

### 续费

再生成一个新到期日的码发过去，客户重新粘贴激活即可。旧码到期自动失效，你不用做任何操作。

### 发现某个码被滥用（被转发给很多人）

在 `wrangler.toml` 的 `BLOCKED_CODES` 里加上该码，重新 `npx wrangler deploy`：

```toml
BLOCKED_CODES = "ZN-20261231-A1B2C3D4,ZN-20270101-99887766"
```

### 查看用量 / 排查问题

```bash
npx wrangler tail           # 实时日志
```
或登录 Cloudflare 控制台 → Workers → zhanno-ai → Metrics 查看调用量。

### 换模型或换供应商

只改 `wrangler.toml` 里的 `AI_PROVIDER` / `AI_MODEL`，重新部署即可，
**客户端不用重新打包、客户不用升级**。

```toml
AI_PROVIDER = "deepseek"      # 或 "minimax"
AI_MODEL = "deepseek-chat"
```

---

## 安全要点

| 项目 | 状态 |
|---|---|
| 大模型 API Key | 只在 Cloudflare Secret 里，客户端与安装包中都没有 |
| 授权码签名密钥 | 只在 Cloudflare Secret 与本机 `.license_secret`，不在代码仓库 |
| 客户伪造授权码 | 不可能——改日期会导致 HMAC 签名不匹配，Worker 拒绝 |
| 客户反编译软件 | 拿不到任何 Key，程序里根本没有 |
| 过期码 | Worker 直接 403，不转发给大模型，**不消耗你的 token** |
| 超长请求刷量 | 单次 >20 条消息或 >20000 字符直接拒绝 |

⚠️ **旧密钥 `zhanno-finance-license-2025-v1-ryankajia` 已泄露在公开仓库中，已废弃。**
用它生成的所有旧授权码都不再被 Worker 接受。
