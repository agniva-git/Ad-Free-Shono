import pytest
from fastapi.testclient import TestClient

from conftest import ADMIN_PW, USER_PW

STRONG_KEY = "k" * 48


# ---------- who gets in ----------

def test_everything_needs_a_login(anon):
    for url in ("/api/songs", "/api/stats", "/api/artists", "/api/albums", "/api/playlists", "/api/search?q=a",
                "/api/songs/x/stream", "/api/artwork/art_x.jpg", "/api/admin/users", "/api/songs/history/recent"):
        assert anon.get(url).status_code == 401, url
    assert anon.post("/api/upload", files={"file": ("a.wav", b"x", "audio/wav")}).status_code == 401
    assert anon.post("/api/scan", json={}).status_code == 401
    assert anon.get("/api/health").status_code == 200
    assert anon.get("/api/auth/status").json() == {"authenticated": False, "user": None}


def test_login_logout_and_status(anon, make_client):
    make_client("bob")
    wrong_pw = anon.post("/api/login", json={"username": "bob", "password": "nope-nope-nope"})
    wrong_user = anon.post("/api/login", json={"username": "nobody", "password": USER_PW})
    assert wrong_pw.status_code == wrong_user.status_code == 401
    assert wrong_pw.json() == wrong_user.json()          # does not reveal which usernames exist

    assert anon.post("/api/login", json={"username": "bob", "password": USER_PW}).status_code == 200
    st = anon.get("/api/auth/status").json()
    assert st["authenticated"] is True and st["user"]["username"] == "bob" and st["user"]["role"] == "member"
    assert "password" not in str(st)

    anon.post("/api/logout")
    assert anon.get("/api/songs").status_code == 401


def test_forged_or_tampered_cookies_are_rejected(anon, make_client, db):
    from backend.app.models import User
    make_client("alice"); make_client("bob")
    alice = db.query(User).filter(User.username == "alice").one()
    bob = db.query(User).filter(User.username == "bob").one()

    bob_client = make_client("bob")
    sig = bob_client.cookies.get("adfree_session").split(".", 1)[1]
    for forged in (f"{alice.id}.{sig}",           # bob's signature on alice's id
                   f"{bob.id}.deadbeef",          # right user, invented signature
                   f"{bob.id}.",                  # missing signature
                   "garbage", ""):
        anon.cookies.clear()
        anon.cookies.set("adfree_session", forged)
        assert anon.get("/api/songs").status_code == 401, forged


def test_login_is_rate_limited_per_visitor(anon, make_client, monkeypatch):
    make_client("bob")
    monkeypatch.setattr("time.sleep", lambda s: None)
    for _ in range(5):
        assert anon.post("/api/login", json={"username": "bob", "password": "wrong-one-xx"}).status_code == 401
    blocked = anon.post("/api/login", json={"username": "bob", "password": USER_PW})   # even the right one
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0


def test_successful_login_resets_the_failure_count(anon, make_client, monkeypatch):
    make_client("bob")
    monkeypatch.setattr("time.sleep", lambda s: None)
    for _ in range(4):
        anon.post("/api/login", json={"username": "bob", "password": "wrong-one-xx"})
    assert anon.post("/api/login", json={"username": "bob", "password": USER_PW}).status_code == 200
    for _ in range(4):
        assert anon.post("/api/login", json={"username": "bob", "password": "wrong-one-xx"}).status_code == 401


def test_cookie_is_secure_only_over_https(app_modules, make_client):
    app, *_ = app_modules
    make_client("bob")
    creds = {"username": "bob", "password": USER_PW}

    http = TestClient(app, base_url="http://testserver")
    cookie = http.post("/api/login", json=creds).headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" not in cookie

    https = TestClient(app, base_url="https://testserver")
    res = https.post("/api/login", json=creds)
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert "strict-transport-security" in res.headers


# ---------- passwords and secrets ----------

def test_passwords_are_stored_hashed_not_plain(make_client, db):
    from backend.app.models import User
    from backend.app.security import verify_password
    make_client("bob")
    stored = db.query(User).filter(User.username == "bob").one().password_hash
    assert USER_PW not in stored and stored.startswith("scrypt$")
    assert verify_password(USER_PW, stored) and not verify_password("other-password-1", stored)
    assert not verify_password(USER_PW, "not-a-valid-hash")


def test_startup_refuses_a_weak_secret_key(app_modules, monkeypatch):
    from backend.app.security import check_security_config
    *_, settings = app_modules
    for bad in ("any-long-random-string", "change-this-to-a-long-random-string", "tooshort", ""):
        monkeypatch.setattr(settings, "SECRET_KEY", bad)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            check_security_config()
    monkeypatch.setattr(settings, "SECRET_KEY", STRONG_KEY)
    check_security_config()


def test_first_start_creates_the_admin_only_with_a_real_password(db, app_modules, monkeypatch):
    from backend.app.models import User
    from backend.app.services.accounts import bootstrap_admin
    *_, settings = app_modules

    for bad in ("", "short", "change-me", "pick-a-password", "admin"):
        monkeypatch.setattr(settings, "ADMIN_PASSWORD", bad)
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            bootstrap_admin(db)
    assert db.query(User).count() == 0

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", ADMIN_PW)
    created = bootstrap_admin(db)
    assert created.username == "admin" and created.role == "admin"

    # later starts never touch an existing admin, even if the .env password differs
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "some-other-password-22")
    assert bootstrap_admin(db) is None
    assert db.query(User).count() == 1


# ---------- the web layer ----------

def test_cross_origin_writes_are_blocked_even_when_logged_in(make_client):
    admin = make_client("admin")
    assert admin.post("/api/playlists", json={"name": "x"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert admin.post("/api/playlists", json={"name": "x"}, headers={"Origin": "http://testserver"}).status_code == 201


def test_no_cors_headers_are_sent(anon):
    assert "access-control-allow-origin" not in anon.get("/api/health", headers={"Origin": "http://evil.example"}).headers


def test_security_headers_on_every_response(anon):
    for url in ("/", "/api/health", "/api/songs"):
        h = anon.get(url).headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert "default-src 'self'" in h["content-security-policy"]
        assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_api_docs_are_hidden_when_not_debugging(anon):
    for url in ("/docs", "/openapi.json", "/redoc"):
        text = anon.get(url).text.lower()
        assert "openapi" not in text and "swagger" not in text


def test_cannot_read_files_outside_the_frontend_folder(anon):
    for url in ("/../backend/app/config.py", "/..%2fbackend/app/config.py", "/%2e%2e/.env"):
        text = anon.get(url).text
        assert "SECRET_KEY" not in text and "ADMIN_PASSWORD" not in text


def test_artwork_is_served_only_to_logged_in_users_and_safely(anon, make_client, app_modules):
    *_, settings = app_modules
    (settings.artwork_path / "art_abc123.jpg").write_bytes(b"\xff\xd8fakejpeg")
    assert anon.get("/api/artwork/art_abc123.jpg").status_code == 401

    bob = make_client("bob")
    ok = bob.get("/api/artwork/art_abc123.jpg")
    assert ok.status_code == 200 and ok.content.startswith(b"\xff\xd8")
    for name in ("missing.jpg", ".env", "a%2f..%2f..%2fetc%2fpasswd", "..%2f..%2fconfig.py"):
        assert bob.get(f"/api/artwork/{name}").status_code == 404

    # the HTTP client tidies ".." away before sending, so check the endpoint itself too
    from fastapi import HTTPException
    from backend.app.api.artwork import get_artwork
    for name in ("..", "../config.py", "/etc/passwd", "a/b.jpg", ""):
        with pytest.raises(HTTPException) as err:
            get_artwork(name)
        assert err.value.status_code == 404
