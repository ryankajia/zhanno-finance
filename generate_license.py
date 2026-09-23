#!/usr/bin/env python3
"""运营工具：生成湛诺财务系统 AI 授权码。

⚠️ 签名密钥不写在代码里。它必须与 Cloudflare Worker 上的 LICENSE_SECRET 完全一致。
   本脚本按以下顺序读取密钥：
     1. 环境变量 ZHANNO_LICENSE_SECRET
     2. 本目录下的 .license_secret 文件（已加入 .gitignore，不会提交）

用法：
  python generate_license.py 2026-12-31              生成一个到期码
  python generate_license.py 2026-10-31 2026-11-30   一次生成多个
  python generate_license.py --month                 生成"一个月后到期"的码（最常用）
"""
import hashlib
import hmac
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_SECRET_FILE = Path(__file__).parent / ".license_secret"


def _secret() -> bytes:
    v = os.getenv("ZHANNO_LICENSE_SECRET")
    if not v and _SECRET_FILE.exists():
        v = _SECRET_FILE.read_text(encoding="utf-8").strip()
    if not v:
        sys.exit(
            "❌ 未找到签名密钥。\n"
            "   请把 Worker 上 LICENSE_SECRET 的同一个值写入文件：\n"
            f"   {_SECRET_FILE}\n"
            "   或设置环境变量 ZHANNO_LICENSE_SECRET"
        )
    return v.encode()


def generate_license(expire_date: str) -> str:
    d8 = expire_date.replace("-", "")
    if len(d8) != 8 or not d8.isdigit():
        raise ValueError(f"日期格式应为 YYYY-MM-DD，收到：{expire_date}")
    datetime.strptime(d8, "%Y%m%d")  # 校验真实日期
    sig = hmac.new(_secret(), f"ZN-{d8}".encode(), hashlib.sha256).hexdigest()[:8].upper()
    return f"ZN-{d8}-{sig}"


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    if args[0] in ("--month", "-m"):
        dates = [(date.today() + timedelta(days=30)).isoformat()]
    elif args[0] in ("--year", "-y"):
        dates = [(date.today() + timedelta(days=365)).isoformat()]
    else:
        dates = args

    print()
    for expire in dates:
        try:
            code = generate_license(expire)
            left = (datetime.strptime(expire, "%Y-%m-%d").date() - date.today()).days
            flag = "✓" if left >= 0 else "已过期"
            print(f"  {flag}  {code}    到期：{expire}（剩 {left} 天）")
        except Exception as e:
            print(f"  ✗  {expire} 错误：{e}")
    print()
    print("  把上面的码发给客户，让他在软件「系统设置 → AI 功能授权」中粘贴激活。")
    print()


if __name__ == "__main__":
    main()
