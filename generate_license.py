#!/usr/bin/env python3
"""
运营工具：生成湛诺财务系统 AI 授权码

用法：
  python generate_license.py 2026-07-04
      → 生成到 2026-07-04 到期的授权码

  python generate_license.py 2026-06-05 2026-07-04
      → 显示"2026-06-05 开始，2026-07-04 到期"（开始日仅供备注，码本身以到期日为准）

  python generate_license.py 2026-07-04 2026-08-03 2026-09-02
      → 一次生成多个到期日的码
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from app.utils.license import generate_license, validate_license


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python generate_license.py 2026-07-04")
        print("      python generate_license.py 2026-06-05 2026-07-04   （开始日 到期日）")
        sys.exit(1)

    # 判断是否"开始日 到期日"两参数模式
    if len(args) == 2:
        try:
            datetime.strptime(args[0], "%Y-%m-%d")
            datetime.strptime(args[1], "%Y-%m-%d")
            start_date, expire_dates = args[0], [args[1]]
        except ValueError:
            start_date, expire_dates = None, args
    else:
        start_date, expire_dates = None, args

    print()
    for expire in expire_dates:
        try:
            code = generate_license(expire)
            check = validate_license(code)
            status = "✓" if check["valid"] else "过期"
            if start_date:
                print(f"  {status}  {code}")
                print(f"       授权区间：{start_date}  →  {expire}")
            else:
                print(f"  {status}  {code}   到期：{expire}")
        except Exception as e:
            print(f"  ✗  {expire} 错误：{e}")
    print()
    print("  发给客户后，让他在软件「系统设置 → AI 功能授权」中粘贴激活。")
    print()


if __name__ == "__main__":
    main()
