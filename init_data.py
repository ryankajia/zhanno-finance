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

    _migrate_db()

    db = SessionLocal()
    try:
        _seed_users(db, get_password_hash)
        _seed_categories(db)
        db.commit()
    finally:
        db.close()

    print("✅ 初始数据就绪")


def _migrate_db():
    """为旧数据库安全添加新字段（幂等）。"""
    from app.database import engine
    from sqlalchemy import text

    add_cols = [
        "ALTER TABLE transactions ADD COLUMN transaction_type TEXT DEFAULT 'expense'",
        "ALTER TABLE categories ADD COLUMN category_type TEXT DEFAULT 'expense'",
    ]
    # 填充旧行的 NULL 值（SQLite ALTER TABLE 不自动回填已有行）
    fill_nulls = [
        "UPDATE transactions SET transaction_type='expense' WHERE transaction_type IS NULL",
        "UPDATE categories SET category_type='expense' WHERE category_type IS NULL",
    ]
    with engine.connect() as conn:
        for sql in add_cols:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # 字段已存在，跳过
        for sql in fill_nulls:
            conn.execute(text(sql))
        conn.commit()


def _seed_users(db, hash_fn):
    from app.models import User

    if db.query(User).count() == 0:
        db.add(User(username="admin", password_hash=hash_fn("123456"), role="admin"))


def _seed_categories(db):
    from app.models import Category

    # (名称, 颜色, 说明, 类型)
    expense_defaults = [
        ("员工薪资",   "#EC4899", "工资、奖金、社保等人力成本",   "expense"),
        ("房租水电",   "#6366F1", "办公室租金、水电网络费用",     "expense"),
        ("市场推广费", "#3B82F6", "广告、推广、品牌活动支出",     "expense"),
        ("客户招待费", "#10B981", "客户接待餐饮、礼品、活动",     "expense"),
        ("差旅费",     "#14B8A6", "出差交通、住宿、餐饮",         "expense"),
        ("办公用品",   "#84CC16", "耗材、设备、办公家具",         "expense"),
        ("软件服务费", "#F97316", "SaaS 订阅、云服务、工具软件",  "expense"),
        ("内部垫资",   "#F59E0B", "合伙人代垫的公司费用",         "expense"),
        ("商业咨询费", "#8B5CF6", "顾问、律师、审计等专业服务",   "expense"),
        ("税费",       "#EF4444", "增值税、企业所得税、印花税等", "expense"),
        ("其他支出",   "#6B7280", "以上分类未涵盖的其他支出",     "expense"),
    ]

    income_defaults = [
        ("项目收入",   "#10B981", "按项目交付结款的收入",         "income"),
        ("服务收入",   "#3B82F6", "持续性服务、维保、订阅收入",   "income"),
        ("产品销售",   "#8B5CF6", "实体或虚拟产品的销售收入",     "income"),
        ("咨询收入",   "#F59E0B", "提供咨询、培训的收入",         "income"),
        ("其他收入",   "#6B7280", "以上分类未涵盖的其他收入",     "income"),
    ]

    for name, color, desc, ctype in expense_defaults + income_defaults:
        existing = db.query(Category).filter(Category.name == name).first()
        if existing:
            # 补全旧数据的 category_type
            if existing.category_type != ctype:
                existing.category_type = ctype
        else:
            db.add(Category(name=name, color=color, description=desc,
                            category_type=ctype, is_system=True))

    # 旧版"其他"兼容：改为支出类型
    old_other = db.query(Category).filter(Category.name == "其他").first()
    if old_other:
        old_other.category_type = "expense"
