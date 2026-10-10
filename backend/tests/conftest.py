"""Test setup: every test run uses a throwaway database and folders, never your real library.
The environment must be set BEFORE the app is imported, which is why this lives in conftest."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="adfree_test_"))
ADMIN_PW = "admin-test-password-1"
USER_PW = "friend-test-password-1"

os.environ.update({
    "DATA_DIR": str(_TMP),
    "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "MUSIC_DIR": str(_TMP / "audio"),
    "ARTWORK_DIR": str(_TMP / "artwork"),
    "SECRET_KEY": "test-secret-key-" + "x" * 40,
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": ADMIN_PW,
    # fixed values so a developer's own .env can never change how the tests behave
    "HOST": "127.0.0.1",
    "DEBUG": "False",
    "MAX_UPLOAD_MB": "500",
    "MEMBER_QUOTA_MB": "5000",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def app_modules():
    from backend.app.main import app
    from backend.app.database import Base, engine, SessionLocal
    from backend.app.config import settings
    return app, Base, engine, SessionLocal, settings


@pytest.fixture(autouse=True)
def clean_state(app_modules):
    """Empty every table (and the media folders) after each test."""
    yield
    _, Base, engine, _, settings = app_modules
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    for folder in (settings.artwork_path, settings.music_path):
        for f in folder.iterdir():
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


@pytest.fixture()
def anon(app_modules):
    """A visitor who is not logged in."""
    app, *_ = app_modules
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make_client(app_modules, db):
    """make_client("bob") creates the account (if needed) and returns a client logged in as them."""
    app, *_ = app_modules
    from backend.app.models import User
    from backend.app.services.accounts import create_user
    opened = []

    def _make(username="admin", role=None, password=None):
        role = role or ("admin" if username == "admin" else "member")
        password = password or (ADMIN_PW if role == "admin" else USER_PW)
        if not db.query(User).filter(User.username == username).first():
            create_user(db, username, password, role=role)
        c = TestClient(app)
        c.__enter__()
        opened.append(c)
        res = c.post("/api/login", json={"username": username, "password": password})
        assert res.status_code == 200, res.text
        return c

    yield _make
    for c in opened:
        c.__exit__(None, None, None)


@pytest.fixture()
def client(make_client):
    """The admin, logged in. Most single-user tests use this."""
    return make_client("admin")
