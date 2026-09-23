"""湛诺财务系统入口 —— python main.py"""
import os
import socket
import sys
import threading
import webbrowser


_LOG_PATH = None


def _log_path():
    return _LOG_PATH


def _data_dir() -> "Path":
    from pathlib import Path
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "湛诺财务系统"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "湛诺财务系统"
    else:
        base = Path.home() / ".湛诺财务系统"
    base.mkdir(parents=True, exist_ok=True)
    return base


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

    global _LOG_PATH
    stream = None
    try:
        base = _data_dir()
        _LOG_PATH = str(base / "run.log")
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


def _alert(title: str, message: str) -> None:
    """在窗口模式下弹出系统对话框。没有控制台时这是唯一能让用户看到问题的方式。"""
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)  # MB_ICONERROR
            return
        if sys.platform == "darwin":
            import subprocess
            subprocess.run([
                "osascript", "-e",
                f'display alert "{title}" message "{message}" as critical',
            ], timeout=30)
            return
    except Exception:
        pass
    print(f"{title}: {message}")


def _find_free_port(preferred: int = 8000) -> int:
    """端口被占用时自动换一个，避免「双击没反应」。"""
    for port in [preferred, 8001, 8002, 8080, 8888, 0]:
        s_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s_.bind(("127.0.0.1", port))
            actual = s_.getsockname()[1]
            return actual
        except OSError:
            continue
        finally:
            s_.close()
    return preferred


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _open_browser(port: int):
    """等服务真正起来再打开浏览器；webbrowser 失败时回退到系统命令。"""
    import time
    import urllib.request

    url = f"http://localhost:{port}"
    for _ in range(40):                      # 最多等 20 秒
        time.sleep(0.5)
        try:
            urllib.request.urlopen(url, timeout=2)
            break
        except Exception:
            continue

    try:
        if webbrowser.open(url):
            return
    except Exception:
        pass
    try:                                      # 回退：交给系统默认处理
        if sys.platform == "win32":
            os.startfile(url)                 # noqa: S606
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", url])
    except Exception:
        pass


if __name__ == "__main__":
    try:
        import uvicorn

        port = _find_free_port(8000)
        ip = _local_ip()

        print("\n" + "=" * 52)
        print("  湛 诺 财 务 系 统  已启动")
        print("=" * 52)
        print(f"  本机访问:   http://localhost:{port}")
        print(f"  局域网访问: http://{ip}:{port}")
        print("=" * 52)
        print("  默认账户: admin  密码: 123456")
        print("  ⚠️  首次登录后请在「设置→用户管理」修改密码！")
        print("=" * 52 + "\n")

        threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
        uvicorn.run(app, host="0.0.0.0", port=port, reload=False, log_config=None)

    except SystemExit:
        raise
    except BaseException as exc:              # 兜底：绝不静默退出
        import traceback
        detail = traceback.format_exc()
        try:
            print(detail)
        except Exception:
            pass
        _alert(
            "湛诺财务系统启动失败",
            f"{type(exc).__name__}: {exc}\n\n"
            "请把以下文件发给客服排查：\n"
            f"{_log_path() or '（日志不可用）'}",
        )
        raise SystemExit(1)
