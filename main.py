"""湛诺财务系统入口 —— python main.py"""
import os
import socket
import sys
import threading
import webbrowser


def _fix_std_streams():
    """Windows 上以窗口模式（console=False）打包运行时，PyInstaller 会把
    sys.stdout / sys.stderr 置为 None。uvicorn 配置日志时会调用
    sys.stdout.isatty()，导致启动即崩溃：
        AttributeError: 'NoneType' object has no attribute 'isatty'
        ValueError: Unable to configure formatter 'default'
    这里把空流接到用户数据目录下的 run.log，既避免崩溃，
    也方便客户报障时让他把这个文件发回来排查。
    """
    if sys.stdout is not None and sys.stderr is not None:
        return

    stream = None
    try:
        from pathlib import Path
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home())) / "湛诺财务系统"
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "湛诺财务系统"
        else:
            base = Path.home() / ".湛诺财务系统"
        base.mkdir(parents=True, exist_ok=True)
        stream = open(base / "run.log", "a", encoding="utf-8", buffering=1)
    except Exception:
        try:
            stream = open(os.devnull, "w")
        except Exception:
            return

    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


# 必须最先执行：后续任何 import 或 print 都可能用到标准输出
_fix_std_streams()

# 必须在所有 app 模块导入前运行，确保 .env 存在
from init_data import bootstrap_env
bootstrap_env()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import create_tables
from app.routers import auth, transactions, categories, ai, reports, settings, users, tax
from app.utils.app_paths import get_static_dir
from init_data import init_data

_STATIC_DIR = str(get_static_dir())


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    init_data()
    yield


app = FastAPI(title="湛诺财务系统", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,         prefix="/api/auth",         tags=["认证"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["账目"])
app.include_router(categories.router,   prefix="/api/categories",   tags=["分类"])
app.include_router(ai.router,           prefix="/api/ai",           tags=["AI"])
app.include_router(reports.router,      prefix="/api/reports",      tags=["报告"])
app.include_router(settings.router,     prefix="/api/settings",     tags=["设置"])
app.include_router(users.router,        prefix="/api/users",        tags=["用户管理"])
app.include_router(tax.router,          prefix="/api/tax",          tags=["税务提醒"])

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
def root():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _open_browser():
    import time
    time.sleep(1.2)
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    import uvicorn

    ip = _local_ip()
    print("\n" + "=" * 52)
    print("  湛 诺 财 务 系 统  已启动")
    print("=" * 52)
    print(f"  本机访问:   http://localhost:8000")
    print(f"  局域网访问: http://{ip}:8000")
    print("=" * 52)
    print("  默认账户: admin  密码: 123456")
    print("  ⚠️  首次登录后请在「设置→用户管理」修改密码！")
    print("=" * 52 + "\n")

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
