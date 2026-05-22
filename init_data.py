"""首次启动时初始化数据库数据（幂等）。"""
import os


def _get_data_dir():
    import sys
    from pathlib import Path
    APP_NAME = "湛诺财务系统"
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        base = Path.home() / f".{APP_NAME}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def bootstrap_env():
    """在任何 app 模块导入之前确保用户数据目录的 .env 存在并有加密密钥。"""
    data_dir = _get_data_dir()
    env_path = data_dir / ".env"
    if env_path.exists():
        return

    from cryptography.fernet import Fernet
    import secrets

    key = Fernet.generate_key().decode()
    secret = secrets.token_hex(32)

    with open(env_path, "w") as f:
        f.write(f"SECRET_KEY={secret}\n")
        f.write(f"ENCRYPTION_KEY={key}\n")
        f.write("MINIMAX_API_KEY=\n")
        f.write("MINIMAX_GROUP_ID=\n")

    print(f"✅ 已自动生成 .env → {env_path}")


def init_data():
    from app.database import SessionLocal
    from app.models import User, Category
    from app.auth import get_password_hash

    db = SessionLocal()
    try:
        _seed_users(db, get_password_hash)
        _seed_categories(db)
        db.commit()
    finally:
        db.close()

    print("✅ 初始数据就绪")


def _seed_users(db, hash_fn):
    from app.models import User

    if db.query(User).count() == 0:
        db.add(User(username="admin", password_hash=hash_fn("123456"), role="admin"))


def _seed_categories(db):
    from app.models import Category

    defaults = [
        ("市场推广费", "#3B82F6", "市场推广相关支出"),
        ("客户招待费", "#10B981", "客户接待餐饮差旅"),
        ("内部垫资",   "#F59E0B", "合伙人代垫费用"),
        ("商业咨询费", "#8B5CF6", "咨询顾问服务费"),
        ("其他",       "#6B7280", "其他支出"),
    ]
    for name, color, desc in defaults:
        if not db.query(Category).filter(Category.name == name).first():
            db.add(Category(name=name, color=color, description=desc, is_system=True))
