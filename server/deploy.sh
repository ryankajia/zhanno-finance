#!/usr/bin/env bash
# 湛诺 AI 中转服务 —— 一键部署到自己的服务器
# 用法：把本文件内容整个粘贴到服务器终端执行（需 root）
set -euo pipefail

SERVER_IP="${SERVER_IP:-43.142.142.229}"
PORT="${PORT:-8443}"
APP_DIR=/opt/zhanno-ai
CFG_DIR=/etc/zhanno-ai

echo "════════════════════════════════════════"
echo "  湛诺 AI 中转服务 部署"
echo "  服务器 IP : $SERVER_IP"
echo "  监听端口  : $PORT (HTTPS)"
echo "════════════════════════════════════════"
echo

[ "$(id -u)" -eq 0 ] || { echo "❌ 请用 root 执行（或 sudo -i 后再粘贴）"; exit 1; }

# ── 1. 依赖 ──────────────────────────────────────────
echo "▶ 安装系统依赖…"
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip openssl curl >/dev/null
elif command -v yum >/dev/null 2>&1; then
  yum install -y -q python3 python3-pip openssl curl >/dev/null
else
  echo "❌ 不认识的系统，请手动安装 python3 / openssl"; exit 1
fi
echo "  ✅ 完成"

# ── 2. 收集密钥 ──────────────────────────────────────
mkdir -p "$CFG_DIR" "$APP_DIR"
chmod 700 "$CFG_DIR"

if [ -f "$CFG_DIR/config.env" ]; then
  echo "▶ 检测到已有配置，跳过密钥输入（如需重填：rm $CFG_DIR/config.env 后重跑）"
else
  echo
  echo "▶ 请依次粘贴三项配置（粘贴时屏幕不显示内容，属正常）"
  echo
  read -rsp "  ① 授权码签名密钥 LICENSE_SECRET : " LICENSE_SECRET; echo
  read -rsp "  ② MiniMax API Key                : " AI_API_KEY; echo
  read -rsp "  ③ MiniMax GroupId                : " MINIMAX_GROUP_ID; echo
  [ -n "$LICENSE_SECRET" ] && [ -n "$AI_API_KEY" ] || { echo "❌ 前两项不能为空"; exit 1; }

  cat > "$CFG_DIR/config.env" <<EOF
LICENSE_SECRET=$LICENSE_SECRET
AI_API_KEY=$AI_API_KEY
MINIMAX_GROUP_ID=$MINIMAX_GROUP_ID
AI_MODEL=abab6.5s-chat
BLOCKED_CODES=
EOF
  chmod 600 "$CFG_DIR/config.env"
  echo "  ✅ 已保存到 $CFG_DIR/config.env（仅 root 可读）"
fi

# ── 3. 自签名证书（把 IP 写进 SAN，客户端才认）──────────
if [ ! -f "$CFG_DIR/server.crt" ]; then
  echo
  echo "▶ 生成自签名证书（有效期 10 年）…"
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout "$CFG_DIR/server.key" -out "$CFG_DIR/server.crt" \
    -subj "/CN=$SERVER_IP/O=Zhanno Finance" \
    -addext "subjectAltName=IP:$SERVER_IP" >/dev/null 2>&1
  chmod 600 "$CFG_DIR/server.key"
  chmod 644 "$CFG_DIR/server.crt"
  echo "  ✅ 完成"
fi

# ── 4. 应用代码 ──────────────────────────────────────
echo "▶ 安装 Python 环境…"
[ -d "$APP_DIR/venv" ] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q fastapi "uvicorn[standard]" httpx pydantic
echo "  ✅ 完成"

# app.py 由部署者放到 $APP_DIR/app.py（见下方 heredoc）
if [ ! -f "$APP_DIR/app.py" ]; then
  echo "❌ 缺少 $APP_DIR/app.py，请先上传应用代码"; exit 1
fi

# ── 5. systemd 常驻 ──────────────────────────────────
echo "▶ 注册开机自启服务…"
cat > /etc/systemd/system/zhanno-ai.service <<EOF
[Unit]
Description=Zhanno AI Proxy
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$CFG_DIR/config.env
ExecStart=$APP_DIR/venv/bin/uvicorn app:app \\
  --host 0.0.0.0 --port $PORT \\
  --ssl-keyfile $CFG_DIR/server.key \\
  --ssl-certfile $CFG_DIR/server.crt
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q zhanno-ai
systemctl restart zhanno-ai
sleep 4
echo "  ✅ 完成"

# ── 6. 自检 ──────────────────────────────────────────
echo
echo "▶ 自检…"
if systemctl is-active --quiet zhanno-ai; then
  echo "  ✅ 服务运行中"
else
  echo "  ❌ 服务未启动，日志："; journalctl -u zhanno-ai -n 30 --no-pager; exit 1
fi

if curl -sk --max-time 10 "https://127.0.0.1:$PORT/health" | grep -q '"ok":true'; then
  echo "  ✅ 本机 HTTPS 响应正常"
else
  echo "  ❌ 本机无响应，日志："; journalctl -u zhanno-ai -n 30 --no-pager; exit 1
fi

echo
echo "════════════════════════════════════════"
echo "  ✅ 部署成功"
echo "════════════════════════════════════════"
echo
echo "请把下面【证书】整段复制发给开发者，用于写进客户端："
echo
echo "-----BEGIN CERT COPY-----"
cat "$CFG_DIR/server.crt"
echo "-----END CERT COPY-----"
echo
echo "常用命令："
echo "  查看状态 : systemctl status zhanno-ai"
echo "  查看日志 : journalctl -u zhanno-ai -f"
echo "  重启     : systemctl restart zhanno-ai"
echo "  停用某码 : 编辑 $CFG_DIR/config.env 的 BLOCKED_CODES 后 systemctl restart zhanno-ai"
echo
