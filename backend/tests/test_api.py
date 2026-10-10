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
