"""统一管理运行时路径：兼容开发模式和 PyInstaller 打包后的模式。"""
import sys
import os
from pathlib import Path

APP_NAME = "湛诺财务系统"


def get_data_dir() -> Path:
    """返回用户数据目录（存放 .env、数据库等可写文件）。"""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        base = Path.home() / f".{APP_NAME}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_static_dir() -> Path:
    """返回 static/ 目录路径（兼容 PyInstaller _MEIPASS）。"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "static"
    return Path(__file__).parent.parent.parent / "static"
