"""Test setup: every test run uses a throwaway database and folders, never your real library.
The environment must be set BEFORE the app is imported, which is why this lives in conftest."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="adfree_test_"))
os.environ.update({
    "DATA_DIR": str(_TMP),
    "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "MUSIC_DIR": str(_TMP / "audio"),
    "ARTWORK_DIR": str(_TMP / "artwork"),
    "ACCESS_PASSWORD": "",
    "SECRET_KEY": "test-secret",
    # fixed values so a developer's own .env can never change how the tests behave
    "HOST": "127.0.0.1",
    "DEBUG": "False",
    "MAX_UPLOAD_MB": "500",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def app_modules():
    from backend.app.main import app
    from backend.app.database import Base, engine, SessionLocal
    from backend.app.config import settings
    return app, Base, engine, SessionLocal, settings


@pytest.fixture()
def client(app_modules):
    app, *_ = app_modules
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_state(app_modules):
    """Empty every table (and the artwork folder) after each test."""
    yield
    _, Base, engine, _, settings = app_modules
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    for f in settings.artwork_path.iterdir():
        f.unlink()
    for f in settings.music_path.iterdir():
        f.unlink()


@pytest.fixture(autouse=True)
def fresh_login_limiter():
    from backend.app.security import reset_login_limiter
    reset_login_limiter()
    yield
    reset_login_limiter()


@pytest.fixture()
def db(app_modules):
    *_, SessionLocal, _ = app_modules
    session = SessionLocal()
    yield session
    session.close()
