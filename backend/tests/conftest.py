"""Test setup: every test run uses a throwaway database and folders, never your real library.
The environment must be set BEFORE the app is imported, which is why this lives in conftest.
"""
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
    "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests",
    # Fixed values so a developer's own .env can never change how the tests behave
    "HOST": "127.0.0.1",
    "DEBUG": "False",
    "MAX_UPLOAD_MB": "500",
    # Bootstrap the initial admin for all tests
    "ADMIN_USERNAME": "testadmin",
    "ADMIN_PASSWORD": "testpassword123",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def app_modules():
    from backend.app.main import app
    from backend.app.database import Base, engine, SessionLocal
    from backend.app.config import settings
    return app, Base, engine, SessionLocal, settings


@pytest.fixture(scope="session")
def admin_client(app_modules):
    """A TestClient already logged in as the test admin (session-scoped, reused across tests)."""
    app, *_ = app_modules
    with TestClient(app) as c:
        res = c.post("/api/login", json={"username": "testadmin", "password": "testpassword123"})
        assert res.status_code == 200, f"Admin login failed: {res.text}"
        yield c


@pytest.fixture()
def client(admin_client):
    """Per-test alias for the session-scoped admin client."""
    return admin_client


@pytest.fixture(autouse=True)
def clean_state(app_modules):
    """Empty every table (except users) and the media folders after each test."""
    yield
    _, Base, engine, _, settings = app_modules
    with engine.begin() as conn:
        # Delete in reverse dependency order; skip the users table to keep testadmin alive
        for table in reversed(Base.metadata.sorted_tables):
            if table.name != "users":
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
