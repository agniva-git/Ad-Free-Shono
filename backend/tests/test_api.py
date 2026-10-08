import io
import os
import wave
from pathlib import Path

import pytest


def make_wav(path: Path | None = None, frames: int = 4000) -> io.BytesIO:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x01" * frames)
    if path:
        path.write_bytes(buf.getvalue())
    buf.seek(0)
    return buf


def upload(client, name="track.wav", **form):
    res = client.post("/api/upload", files={"file": (name, make_wav(), "audio/wav")}, data=form)
    assert res.status_code == 201, res.text
    return res.json()


# ---------- basics ----------

def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_stats_empty_library(client):
    data = client.get("/api/stats").json()
    assert data["total_songs"] == 0 and data["total_artists"] == 0


def test_upload_patch_search_history_and_delete(client):
    song = upload(client, title="Original", artist="Alpha Performer", album="Alpha Album")
    sid = song["id"]
    assert song["title"] == "Original" and song["artist_name"] == "Alpha Performer"

    patched = client.patch(f"/api/songs/{sid}", json={
        "title": "Renamed", "artist_name": "New Performer", "album_title": "New Album", "genre": "Synthwave"
    }).json()
    assert patched["title"] == "Renamed" and patched["genre"] == "Synthwave"

    assert len(client.get("/api/search?q=Performer").json()["songs"]) == 1

    assert client.post(f"/api/songs/{sid}/history").status_code == 200
    assert any(s["id"] == sid for s in client.get("/api/songs/history/recent").json())

    res = client.delete(f"/api/songs/{sid}")
    assert res.status_code == 200
    assert client.get(f"/api/songs/{sid}").status_code == 404


def test_favorite_toggle(client):
    sid = upload(client)["id"]
    assert client.post(f"/api/songs/{sid}/favorite").json()["is_favorite"] is True
    assert len(client.get("/api/songs?favorites_only=true").json()) == 1
    assert client.post(f"/api/songs/{sid}/favorite").json()["is_favorite"] is False


def test_favorite_is_per_user(app_modules, admin_client):
    """Two different users should have independent favorites."""
    app, *_ = app_modules
    from fastapi.testclient import TestClient

    # Create a second user via admin
    admin_client.post("/api/auth/register", json={
        "username": "user2", "password": "secondpass123", "is_admin": False
    })

    # Upload a song as admin
    sid = upload(admin_client)["id"]

    # Admin favorites it
    assert admin_client.post(f"/api/songs/{sid}/favorite").json()["is_favorite"] is True

    # user2 logs in and checks — should NOT see it as favorite
    with TestClient(app) as c2:
        c2.post("/api/login", json={"username": "user2", "password": "secondpass123"})
        resp = c2.get(f"/api/songs/{sid}").json()
        assert resp["is_favorite"] is False
        assert c2.get("/api/songs?favorites_only=true").json() == []


def test_playlist_workflow(client):
    pid = client.post("/api/playlists", json={"name": "Night Drive"}).json()["id"]
    sid = upload(client, title="Midnight City", artist="M83")["id"]
    assert client.post(f"/api/playlists/{pid}/songs", json={"song_id": sid}).status_code == 200
    pl = client.get(f"/api/playlists/{pid}").json()
    assert pl["song_count"] == 1 and pl["songs"][0]["id"] == sid
    assert client.delete(f"/api/playlists/{pid}/songs/{sid}").status_code == 200
    assert client.delete(f"/api/playlists/{pid}").status_code == 200


def test_playlists_are_private(app_modules, admin_client):
    """user2 should not be able to see or touch admin's playlists."""
    app, *_ = app_modules
    from fastapi.testclient import TestClient

    # Ensure user2 exists (idempotent)
    admin_client.post("/api/auth/register", json={
        "username": "user2", "password": "secondpass123", "is_admin": False
    })

    # Admin creates a playlist
    pid = admin_client.post("/api/playlists", json={"name": "Admin Secret"}).json()["id"]

    with TestClient(app) as c2:
        c2.post("/api/login", json={"username": "user2", "password": "secondpass123"})
        # user2's playlist list should be empty
        assert c2.get("/api/playlists").json() == []
        # user2 cannot read admin's playlist
        assert c2.get(f"/api/playlists/{pid}").status_code == 404
        # user2 cannot delete admin's playlist
        assert c2.delete(f"/api/playlists/{pid}").status_code == 404


# ---------- streaming ----------

def test_range_streaming(client):
    sid = upload(client)["id"]
    url = f"/api/songs/{sid}/stream"

    full = client.get(url)
    assert full.status_code == 200
    size = len(full.content)
    assert full.headers["accept-ranges"] == "bytes"

    part = client.get(url, headers={"Range": "bytes=0-49"})
    assert part.status_code == 206 and len(part.content) == 50
    assert part.headers["content-range"] == f"bytes 0-49/{size}"

    suffix = client.get(url, headers={"Range": "bytes=-100"})
    assert suffix.status_code == 206 and suffix.content == full.content[-100:]

    clamped = client.get(url, headers={"Range": "bytes=10-99999999"})
    assert clamped.status_code == 206 and clamped.content == full.content[10:]

    open_ended = client.get(url, headers={"Range": f"bytes={size - 5}-"})
    assert open_ended.content == full.content[-5:]

    assert client.get(url, headers={"Range": f"bytes={size + 10}-"}).status_code == 416
    assert client.get(url, headers={"Range": "garbage"}).status_code == 200


# ---------- deletion ----------

def test_deleting_uploaded_song_removes_its_stored_file_and_empties(client, app_modules):
    *_, settings = app_modules
    song = upload(client, artist="Solo", album="Only Album")
    stored = list(settings.music_path.iterdir())
    assert len(stored) == 1

    res = client.delete(f"/api/songs/{song['id']}").json()
    assert res["file_deleted"] is True
    assert not stored[0].exists()
    # no ghost artist/album left behind
    assert client.get("/api/artists").json() == []
    assert client.get("/api/albums").json() == []


def test_deleting_scanned_song_never_touches_the_original_file(client, tmp_path):
    folder = tmp_path / "MyMusic"
    folder.mkdir()
    original = folder / "precious.wav"
    make_wav(original)

    scan = client.post("/api/scan", json={"directory_path": str(folder)}).json()
    assert scan["added"] == 1
    sid = client.get("/api/songs").json()[0]["id"]

    res = client.delete(f"/api/songs/{sid}?delete_file=true").json()
    assert res["file_deleted"] is False
    assert original.exists(), "the user's own file must survive deleting it from the library"
    assert client.get(f"/api/songs/{sid}").status_code == 404


def test_delete_cleans_history_favorites_and_playlist_rows(client, db):
    from backend.app.models import PlayHistory, Favorite, PlaylistSong
    sid = upload(client)["id"]
    pid = client.post("/api/playlists", json={"name": "P"}).json()["id"]
    client.post(f"/api/songs/{sid}/history")
    client.post(f"/api/songs/{sid}/favorite")
    client.post(f"/api/playlists/{pid}/songs", json={"song_id": sid})

    client.delete(f"/api/songs/{sid}")
    assert db.query(PlayHistory).count() == 0
    assert db.query(Favorite).count() == 0
    assert db.query(PlaylistSong).count() == 0


def test_editing_artist_prunes_the_old_empty_one(client):
    sid = upload(client, artist="Old Name", album="Old Album")["id"]
    client.patch(f"/api/songs/{sid}", json={"artist_name": "New Name", "album_title": "New Album"})
    names = [a["name"] for a in client.get("/api/artists").json()]
    assert names == ["New Name"]


def test_prune_empty_clears_old_leftovers(client, db, app_modules):
    from backend.app.models import Artist, Album, PlayHistory
    from backend.app.services.library import prune_empty, sweep_unused_artwork
    *_, settings = app_modules

    # Grab any user id for the orphan play_history row
    from backend.app.models import User
    user = db.query(User).first()

    # Old databases were created with foreign keys off, so orphan rows could exist.
    db.connection().exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        db.add(Artist(name="Ghost")); db.flush()
        db.add(Album(title="Ghost Album"))
        db.add(PlayHistory(song_id="missing-song", user_id=user.id))
        db.commit()
    finally:
        db.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    (settings.artwork_path / "art_unused.jpg").write_bytes(b"x")

    result = prune_empty(db)
    assert result["artists_removed"] == 1 and result["albums_removed"] == 1
    assert db.query(PlayHistory).count() == 0
    assert sweep_unused_artwork(db) == 1


# ---------- scanner safety ----------

def test_is_safe_directory(tmp_path):
    from backend.app.services.scanner import is_safe_directory
    assert is_safe_directory(tmp_path)
    assert not is_safe_directory(Path(tmp_path.anchor))
    if os.name == "nt":
        assert not is_safe_directory(Path(os.environ.get("SystemRoot", r"C:\Windows")))
    else:
        assert not is_safe_directory(Path("/etc"))
        assert not is_safe_directory(Path("/usr/lib"))


def test_scan_endpoint_rejects_system_and_missing_folders(client, tmp_path):
    restricted = os.environ.get("SystemRoot", r"C:\Windows") if os.name == "nt" else "/etc"
    assert client.post("/api/scan", json={"directory_path": restricted}).status_code == 403
    assert client.post("/api/scan", json={"directory_path": str(tmp_path / "nope")}).status_code == 400


# ---------- upload limits ----------

def test_upload_over_limit_is_rejected_and_leaves_no_file(client, app_modules, monkeypatch):
    *_, settings = app_modules
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0)
    res = client.post("/api/upload", files={"file": ("big.wav", make_wav(), "audio/wav")})
    assert res.status_code == 413
    assert list(settings.music_path.iterdir()) == []


def test_upload_rejects_unknown_extension(client):
    res = client.post("/api/upload", files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")})
    assert res.status_code == 400


# ---------- auth ----------

def test_auth_status_when_logged_in(client):
    data = client.get("/api/auth/status").json()
    assert data["authenticated"] is True
    assert data["username"] == "testadmin"
    assert data["is_admin"] is True


def test_unauthenticated_request_is_rejected(app_modules):
    from fastapi.testclient import TestClient
    app, *_ = app_modules
    with TestClient(app) as c:
        assert c.get("/api/songs").status_code == 401
        assert c.get("/api/stats").status_code == 401
        assert c.get("/api/health").status_code == 200  # health is public


def test_wrong_password_is_rejected(app_modules):
    from fastapi.testclient import TestClient
    app, *_ = app_modules
    with TestClient(app) as c:
        assert c.post("/api/login", json={"username": "testadmin", "password": "wrongpass"}).status_code == 401


def test_login_is_rate_limited(app_modules):
    from fastapi.testclient import TestClient
    import unittest.mock
    app, *_ = app_modules
    with TestClient(app) as c:
        with unittest.mock.patch("time.sleep"):
            for _ in range(5):
                c.post("/api/login", json={"username": "testadmin", "password": "nope"})
            blocked = c.post("/api/login", json={"username": "testadmin", "password": "testpassword123"})
            assert blocked.status_code == 429
            assert int(blocked.headers["retry-after"]) > 0


def test_cross_origin_writes_are_blocked(client):
    evil = {"Origin": "http://evil.example"}
    assert client.post("/api/playlists", json={"name": "x"}, headers=evil).status_code == 403
    same = {"Origin": "http://testserver"}
    assert client.post("/api/playlists", json={"name": "x"}, headers=same).status_code == 201


def test_no_cors_headers_are_sent(client):
    res = client.get("/api/stats", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in res.headers


def test_logout_invalidates_session(app_modules):
    from fastapi.testclient import TestClient
    app, *_ = app_modules
    with TestClient(app) as c:
        c.post("/api/login", json={"username": "testadmin", "password": "testpassword123"})
        assert c.get("/api/songs").status_code == 200
        c.post("/api/logout")
        assert c.get("/api/songs").status_code == 401


def test_admin_can_create_and_delete_users(client):
    res = client.post("/api/auth/register", json={
        "username": "newuser", "password": "newpassword123", "is_admin": False
    })
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "newuser" and data["is_admin"] is False

    users = client.get("/api/auth/users").json()
    assert any(u["username"] == "newuser" for u in users)

    del_res = client.delete(f"/api/auth/users/{data['id']}")
    assert del_res.status_code == 200


def test_non_admin_cannot_register_users(app_modules, admin_client):
    from fastapi.testclient import TestClient
    app, *_ = app_modules

    # Create a non-admin
    admin_client.post("/api/auth/register", json={
        "username": "plainuser", "password": "plainpass123", "is_admin": False
    })

    with TestClient(app) as c:
        c.post("/api/login", json={"username": "plainuser", "password": "plainpass123"})
        res = c.post("/api/auth/register", json={
            "username": "anotherone", "password": "anotherpass123"
        })
        assert res.status_code == 403


# ---------- security headers ----------

def test_security_headers_on_every_response(client):
    for url in ("/", "/api/health", "/api/songs"):
        h = client.get(url).headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        assert "default-src 'self'" in h["content-security-policy"]
        assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_api_docs_are_hidden_when_not_debugging(client):
    for url in ("/docs", "/openapi.json", "/redoc"):
        res = client.get(url)
        assert "openapi" not in res.text.lower() and "swagger" not in res.text.lower()


def test_cannot_read_files_outside_the_frontend_folder(client):
    for url in ("/../backend/app/config.py", "/..%2fbackend/app/config.py", "/%2e%2e/.env"):
        res = client.get(url)
        assert "SECRET_KEY" not in res.text


# ---------- startup check ----------

def test_startup_check_refuses_weak_secret_key(app_modules, monkeypatch):
    from backend.app.security import check_security_config
    *_, settings = app_modules

    def attempt(**values):
        for k, v in values.items():
            monkeypatch.setattr(settings, k, v)
        check_security_config()

    STRONG_KEY = "k" * 48
    for bad_key in ("any-long-random-string", "change-this-to-a-long-random-string", "tooshort", ""):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            attempt(SECRET_KEY=bad_key)
    attempt(SECRET_KEY=STRONG_KEY)  # good key passes


# ---------- cookie security ----------

def test_cookie_is_secure_only_over_https(app_modules, monkeypatch):
    from fastapi.testclient import TestClient
    app, *_, settings = app_modules

    http = TestClient(app, base_url="http://testserver")
    cookie = http.post("/api/login", json={"username": "testadmin", "password": "testpassword123"}).headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" not in cookie

    https = TestClient(app, base_url="https://testserver")
    res = https.post("/api/login", json={"username": "testadmin", "password": "testpassword123"})
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert "strict-transport-security" in res.headers
