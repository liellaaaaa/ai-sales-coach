"""pytest 共享夹具：隔离数据库与环境后再 import app。"""
import os
import sys
import tempfile
from pathlib import Path

# 必须在 import app.* 之前设置，否则 import 期 create_all 会连生产库
_DB_PATH = Path(tempfile.gettempdir()) / "sales_coach_pytest.db"
if _DB_PATH.exists():
    _DB_PATH.unlink()
os.environ["SALES_COACH_DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ.setdefault("SALES_COACH_DEEPSEEK_API_KEY", "")
os.environ.setdefault("SALES_COACH_MIMO_API_KEY", "")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    from app.db.session import Base, SessionLocal, engine
    from app.seed import main as seed_main

    Base.metadata.create_all(bind=engine)
    seed_main()
    yield
    SessionLocal().close()
    engine.dispose()
    try:
        _DB_PATH.unlink()
    except OSError:
        pass


@pytest.fixture()
def db():
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
