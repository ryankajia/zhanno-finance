#!/usr/bin/env python3
"""
运营工具：生成湛诺财务系统 AI 月费授权码

用法：
  python generate_license.py 2025-06
  python generate_license.py 2025-06 2025-07 2025-08   （一次生成多个月）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.utils.license import generate_license, validate_license


def main():
    months = sys.argv[1:]
    if not months:
        print("用法: python generate_license.py 2025-06")
        print("      python generate_license.py 2025-06 2025-07 2025-08")
        sys.exit(1)

    print()
    for ym in months:
        try:
            code = generate_license(ym)
            check = validate_license(code)
            status = "✓" if check["valid"] else "!"
            print(f"  {status}  {code}   有效期：{ym} 月底到期")
        except Exception as e:
            print(f"  ✗  {ym} 格式错误：{e}")
    print()
    print("  发给客户后，让他在软件「系统设置 → AI 授权」中粘贴输入。")
    print()


if __name__ == "__main__":
    main()
