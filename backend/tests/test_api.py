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


def test_playlist_workflow(client):
    pid = client.post("/api/playlists", json={"name": "Night Drive"}).json()["id"]
    sid = upload(client, title="Midnight City", artist="M83")["id"]
    assert client.post(f"/api/playlists/{pid}/songs", json={"song_id": sid}).status_code == 200
    pl = client.get(f"/api/playlists/{pid}").json()
    assert pl["song_count"] == 1 and pl["songs"][0]["id"] == sid
    assert client.delete(f"/api/playlists/{pid}/songs/{sid}").status_code == 200
    assert client.delete(f"/api/playlists/{pid}").status_code == 200


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


# ---------- deleting: the bug that removed your original files ----------

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

    # Old databases were created with foreign keys off, so orphan rows could exist.
    db.connection().exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        db.add(Artist(name="Ghost")); db.flush()
        db.add(Album(title="Ghost Album")); db.add(PlayHistory(song_id="missing-song"))
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


# ---------- login + cross-site protection ----------

@pytest.fixture()
def locked(app_modules, monkeypatch):
    *_, settings = app_modules
    monkeypatch.setattr(settings, "ACCESS_PASSWORD", "hunter2")


def test_login_required_when_password_set(client, locked):
    assert client.get("/api/songs").status_code == 401
    assert client.get("/api/songs/anything/stream").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/status").json() == {"auth_required": True, "authenticated": False}

    assert client.post("/api/login", json={"password": "wrong"}).status_code == 401
    assert client.get("/api/songs").status_code == 401

    assert client.post("/api/login", json={"password": "hunter2"}).status_code == 200
    assert client.get("/api/songs").status_code == 200
    assert client.get("/api/auth/status").json()["authenticated"] is True

    client.post("/api/logout")
    assert client.get("/api/songs").status_code == 401


def test_cross_origin_writes_are_blocked_even_when_logged_in(client, locked):
    client.post("/api/login", json={"password": "hunter2"})
    evil = {"Origin": "http://evil.example"}
    assert client.post("/api/playlists", json={"name": "x"}, headers=evil).status_code == 403
    same = {"Origin": "http://testserver"}
    assert client.post("/api/playlists", json={"name": "x"}, headers=same).status_code == 201


def test_no_cors_headers_are_sent(client):
    res = client.get("/api/stats", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in res.headers


# ---------- public-hosting protections ----------

STRONG_PW = "correct horse battery staple"
STRONG_KEY = "k" * 48


def test_startup_check_refuses_unsafe_settings(app_modules, monkeypatch):
    from backend.app.security import check_security_config
    *_, settings = app_modules

    def attempt(**values):
        for k, v in values.items():
            monkeypatch.setattr(settings, k, v)
        check_security_config()

    # open server with no password is refused
    with pytest.raises(RuntimeError, match="ACCESS_PASSWORD is empty"):
        attempt(HOST="0.0.0.0", ACCESS_PASSWORD="")
    # localhost with no password is allowed
    attempt(HOST="127.0.0.1", ACCESS_PASSWORD="")
    # placeholder / short / common passwords are refused
    for bad in ("pick-a-password", "change-me-please", "short", "hunter2", "password"):
        with pytest.raises(RuntimeError, match="ACCESS_PASSWORD"):
            attempt(HOST="0.0.0.0", ACCESS_PASSWORD=bad, SECRET_KEY=STRONG_KEY)
    # weak or placeholder secret keys are refused
    for bad_key in ("any-long-random-string", "change-this-to-a-long-random-string", "tooshort", ""):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            attempt(HOST="0.0.0.0", ACCESS_PASSWORD=STRONG_PW, SECRET_KEY=bad_key)
    # a good setup passes
    attempt(HOST="0.0.0.0", ACCESS_PASSWORD=STRONG_PW, SECRET_KEY=STRONG_KEY)


def test_login_is_rate_limited(client, app_modules, monkeypatch):
    *_, settings = app_modules
    monkeypatch.setattr(settings, "ACCESS_PASSWORD", STRONG_PW)
    monkeypatch.setattr("time.sleep", lambda s: None)  # keep the test fast

    for _ in range(5):
        assert client.post("/api/login", json={"password": "nope"}).status_code == 401
    blocked = client.post("/api/login", json={"password": STRONG_PW})  # even the right password
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert client.get("/api/songs").status_code == 401


def test_successful_login_resets_the_failure_count(client, app_modules, monkeypatch):
    *_, settings = app_modules
    monkeypatch.setattr(settings, "ACCESS_PASSWORD", STRONG_PW)
    monkeypatch.setattr("time.sleep", lambda s: None)
    for _ in range(4):
        client.post("/api/login", json={"password": "nope"})
    assert client.post("/api/login", json={"password": STRONG_PW}).status_code == 200
    for _ in range(4):
        assert client.post("/api/login", json={"password": "nope"}).status_code == 401


def test_cookie_is_secure_only_over_https(app_modules, monkeypatch):
    from fastapi.testclient import TestClient
    app, *_, settings = app_modules
    monkeypatch.setattr(settings, "ACCESS_PASSWORD", STRONG_PW)

    http = TestClient(app, base_url="http://testserver")
    cookie = http.post("/api/login", json={"password": STRONG_PW}).headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" not in cookie

    https = TestClient(app, base_url="https://testserver")
    res = https.post("/api/login", json={"password": STRONG_PW})
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert "strict-transport-security" in res.headers


def test_security_headers_on_every_response(client):
    for url in ("/", "/api/health", "/api/songs"):  # page, public API, and a blocked-or-open API route
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
        assert "ACCESS_PASSWORD" not in res.text and "SECRET_KEY" not in res.text
