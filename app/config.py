import os
from pathlib import Path
from dotenv import load_dotenv
from app.utils.app_paths import get_data_dir

_data_dir = get_data_dir()
load_dotenv(_data_dir / ".env")

SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-secret")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

_db_path = _data_dir / "zhanno_finance.db"
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{_db_path}")
ENCRYPTION_KEY: str | None = os.getenv("ENCRYPTION_KEY")

from app.utils.bundled_config import BUNDLED_MINIMAX_KEY, BUNDLED_MINIMAX_GROUP_ID
MINIMAX_API_KEY: str | None = os.getenv("MINIMAX_API_KEY") or BUNDLED_MINIMAX_KEY or None
MINIMAX_GROUP_ID: str | None = os.getenv("MINIMAX_GROUP_ID") or BUNDLED_MINIMAX_GROUP_ID or None
