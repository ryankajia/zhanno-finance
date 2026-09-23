#!/usr/bin/env python3
"""运营工具：生成湛诺财务系统 AI 授权码。

每个码都带一个随机编号，因此**即使到期日相同，每个客户拿到的码也不一样**：
  ZN-20261023-7K2M-A1B2C3D4
     └─到期日─┘ └编号┘ └─签名─┘

好处：谁把码传出去了一查台账就知道，封掉他一个不影响其他客户。
所有发出去的码会自动记到 licenses.csv（不会提交到 GitHub）。

⚠️ 签名密钥不写在代码里，必须与 Cloudflare Worker 上的 LICENSE_SECRET 一致。
   读取顺序：环境变量 ZHANNO_LICENSE_SECRET → 本目录 .license_secret 文件

用法：
  python3 generate_license.py --month 张三          一个月后到期，备注客户名
  python3 generate_license.py --year 李四           一年后到期
  python3 generate_license.py 2026-12-31 王五       指定到期日
  python3 generate_license.py --list                查看已发出的所有码
"""
import csv
import hashlib
import hmac
import os
import secrets
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_DIR = Path(__file__).parent
_SECRET_FILE = _DIR / ".license_secret"
_LEDGER = _DIR / "licenses.csv"

# 去掉容易看错的字符：0/O、1/I/L
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _secret() -> bytes:
    v = os.getenv("ZHANNO_LICENSE_SECRET")
    if not v and _SECRET_FILE.exists():
        v = _SECRET_FILE.read_text(encoding="utf-8").strip()
    if not v:
        sys.exit(
            "❌ 未找到签名密钥。\n"
            "   请把 Worker 上 LICENSE_SECRET 的同一个值写入：\n"
            f"   {_SECRET_FILE}\n"
            "   或设置环境变量 ZHANNO_LICENSE_SECRET"
        )
    return v.encode()


def _sign(d8: str, serial: str) -> str:
    msg = f"ZN-{d8}-{serial}".encode()
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()[:8].upper()


def generate_license(expire_date: str, serial: str | None = None) -> str:
    d8 = expire_date.replace("-", "")
    if len(d8) != 8 or not d8.isdigit():
        raise ValueError(f"日期格式应为 YYYY-MM-DD，收到：{expire_date}")
    datetime.strptime(d8, "%Y%m%d")
    if serial is None:
        serial = "".join(secrets.choice(_ALPHABET) for _ in range(4))
    return f"ZN-{d8}-{serial}-{_sign(d8, serial)}"


def _record(code: str, expire: str, customer: str):
    new = not _LEDGER.exists()
    with open(_LEDGER, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["发放日期", "授权码", "到期日", "客户", "备注"])
        w.writerow([date.today().isoformat(), code, expire, customer, ""])


def _list_all():
    if not _LEDGER.exists():
        print("\n  还没有发出过授权码。\n")
        return
    rows = list(csv.DictReader(open(_LEDGER, encoding="utf-8-sig")))
    print(f"\n  共发出 {len(rows)} 个授权码：\n")
    today = date.today().isoformat()
    for r in rows:
        status = "已过期" if today > r["到期日"] else "有效"
        mark = "  " if status == "有效" else "✗ "
        print(f"  {mark}{r['授权码']}  到期 {r['到期日']}  [{status}]  {r['客户'] or '（未备注）'}")
    print()


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    if args[0] == "--list":
        _list_all()
        return

    if args[0] in ("--month", "-m"):
        expire = (date.today() + timedelta(days=30)).isoformat()
        customer = args[1] if len(args) > 1 else ""
    elif args[0] in ("--year", "-y"):
        expire = (date.today() + timedelta(days=365)).isoformat()
        customer = args[1] if len(args) > 1 else ""
    else:
        expire = args[0]
        customer = args[1] if len(args) > 1 else ""

    try:
        code = generate_license(expire)
    except Exception as e:
        sys.exit(f"  ✗ 错误：{e}")

    left = (datetime.strptime(expire, "%Y-%m-%d").date() - date.today()).days
    _record(code, expire, customer)

    print()
    print(f"  ┌{'─' * 40}┐")
    print(f"  │  {code}{' ' * (38 - len(code) - 1)}│")
    print(f"  └{'─' * 40}┘")
    print(f"     到期：{expire}（{left} 天后）")
    if customer:
        print(f"     客户：{customer}")
    print()
    print("  把上面这一串发给客户，让他在软件")
    print("  「系统设置 → AI 功能授权」中粘贴，点激活。")
    print()
    print(f"  已记入台账：{_LEDGER.name}（查看：python3 generate_license.py --list）")
    print()


if __name__ == "__main__":
    main()
