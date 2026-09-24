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


# ── 浏览器关闭后自动退出 ─────────────────────────────────────
# 窗口模式的程序没有界面，客户关掉浏览器时进程仍在后台运行，
# 会一直锁住程序文件夹（提示"已在另一个程序中打开"）。
# 做法：每个打开的页面每 10 秒发一次心跳，页面关闭时发一次"告别"；
# 所有页面都消失且超过宽限期，就自动退出。
import time

_TABS: dict = {}                              # 页面ID -> 最近一次心跳时间
_WATCH = {"ever": False, "empty_since": None, "started": time.monotonic()}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@app.get("/api/ping")
def ping():
    """供第二次双击启动时探测「是不是已经有一个在运行」。"""
    return {"ok": True, "app": "zhanno-finance"}


@app.post("/api/heartbeat")
def heartbeat(t: str = ""):
    if t:
        if len(_TABS) > 200:                  # 防止局域网内被刷爆内存
            _TABS.pop(next(iter(_TABS)), None)
        _TABS[t[:64]] = time.monotonic()
        _WATCH["ever"] = True
        _WATCH["empty_since"] = None
    return {"ok": True}


@app.post("/api/bye")
def bye(t: str = ""):
    _TABS.pop(t[:64], None)
    return {"ok": True}


def _watchdog():
    stale = _env_int("ZHANNO_STALE_SECONDS", 180)    # 页面失联多久视为已消失
    grace = _env_int("ZHANNO_BYE_GRACE", 8)          # 最后一个页面消失后的宽限期
    never = _env_int("ZHANNO_NEVER_SECONDS", 600)    # 一直没人打开页面就退出
    last = time.monotonic()
    while True:
        time.sleep(1)
        now = time.monotonic()
        if now - last > 30:                   # 电脑休眠/挂起后恢复，别误判
            for k in list(_TABS):
                _TABS[k] = now
            _WATCH["empty_since"] = None
            _WATCH["started"] = now
        last = now

        for k, v in list(_TABS.items()):
            if now - v > stale:
                _TABS.pop(k, None)

        if _TABS:
            _WATCH["empty_since"] = None
        elif _WATCH["ever"]:
            if _WATCH["empty_since"] is None:
                _WATCH["empty_since"] = now
            elif now - _WATCH["empty_since"] >= grace:
                print("浏览器已关闭，程序自动退出")
                os._exit(0)
        elif now - _WATCH["started"] > never:
            print("长时间无人使用，程序自动退出")
            os._exit(0)


def _already_running(port: int = 8000) -> bool:
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:
            return json.loads(r.read()).get("app") == "zhanno-finance"
    except Exception:
        return False


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

    if os.environ.get("ZHANNO_NO_BROWSER"):
        return
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

        # 已经有一个在运行：直接打开它，不再重复启动第二个
        for _p in (8000, 8001, 8002, 8080, 8888):
            if _already_running(_p):
                _open_browser(_p)
                raise SystemExit(0)

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
        if getattr(sys, "frozen", False) or os.environ.get("ZHANNO_AUTO_EXIT"):
            threading.Thread(target=_watchdog, daemon=True).start()
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
