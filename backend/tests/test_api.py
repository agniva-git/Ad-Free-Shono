import io
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def create_sample_wav_bytes() -> io.BytesIO:
    wav_header = bytearray([
        0x52, 0x49, 0x46, 0x46,  # 'RIFF'
        0x8C, 0x00, 0x00, 0x00,  # Chunk size: 140
        0x57, 0x41, 0x56, 0x45,  # 'WAVE'
        0x66, 0x6D, 0x74, 0x20,  # 'fmt '
        0x10, 0x00, 0x00, 0x00,  # Subchunk1Size: 16
        0x01, 0x00,              # AudioFormat: 1 (PCM)
        0x01, 0x00,              # NumChannels: 1
        0x44, 0xAC, 0x00, 0x00,  # SampleRate: 44100
        0x88, 0x58, 0x01, 0x00,  # ByteRate: 88200
        0x02, 0x00,              # BlockAlign: 2
        0x10, 0x00,              # BitsPerSample: 16
        0x64, 0x61, 0x74, 0x61,  # 'data'
        0x64, 0x00, 0x00, 0x00   # Subchunk2Size: 100
    ]) + bytearray(100)
    return io.BytesIO(wav_header)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "AdFreeShono"

def test_library_stats():
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_songs" in data
    assert "total_artists" in data

def test_upload_patch_and_stream():
    audio_file = create_sample_wav_bytes()

    # 1. Upload audio
    upload_res = client.post(
        "/api/upload",
        files={"file": ("track_alpha.wav", audio_file, "audio/wav")},
        data={"title": "Original Title", "artist": "Alpha Performer", "album": "Alpha Album"}
    )
    assert upload_res.status_code == 201
    song = upload_res.json()
    song_id = song["id"]
    assert song["title"] == "Original Title"
    assert song["artist_name"] == "Alpha Performer"

    # 2. HTTP Range Streaming (206 Partial Content)
    stream_res = client.get(
        f"/api/songs/{song_id}/stream",
        headers={"Range": "bytes=0-49"}
    )
    assert stream_res.status_code == 206
    assert "Content-Range" in stream_res.headers
    assert stream_res.headers["Content-Range"].startswith("bytes 0-49/")
    assert len(stream_res.content) == 50

    # 3. Patch Metadata (Problem 2 & 8)
    patch_res = client.patch(
        f"/api/songs/{song_id}",
        json={"title": "Renamed Title", "artist_name": "New Performer", "album_title": "New Album", "genre": "Synthwave"}
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["title"] == "Renamed Title"
    assert updated["artist_name"] == "New Performer"
    assert updated["genre"] == "Synthwave"

    # 4. Search verification (matches by title and artist)
    search_res = client.get("/api/search?q=Synthwave")
    assert search_res.status_code == 200

    search_by_artist = client.get("/api/search?q=Performer")
    assert search_by_artist.status_code == 200
    assert len(search_by_artist.json()["songs"]) > 0

    # 5. Play History & Recently Played (Problem 5 & 11)
    hist_record = client.post(f"/api/songs/{song_id}/history")
    assert hist_record.status_code == 200

    recent_res = client.get("/api/songs/history/recent")
    assert recent_res.status_code == 200
    recent_list = recent_res.json()
    assert len(recent_list) > 0
    assert any(s["id"] == song_id for s in recent_list)

    # 6. Delete Song (Problem 6 & 12)
    del_res = client.delete(f"/api/songs/{song_id}?delete_file=true")
    assert del_res.status_code == 200

    # Verify 404 after deletion
    assert client.get(f"/api/songs/{song_id}").status_code == 404

def test_playlist_full_workflow():
    # Create playlist
    p_res = client.post("/api/playlists", json={"name": "Night Drive", "description": "Synth and chill"})
    assert p_res.status_code == 201
    playlist_id = p_res.json()["id"]

    # Upload temporary track
    audio = create_sample_wav_bytes()
    upload_res = client.post(
        "/api/upload",
        files={"file": ("night_track.wav", audio, "audio/wav")},
        data={"title": "Midnight City", "artist": "M83"}
    )
    song_id = upload_res.json()["id"]

    # Add song to playlist (Problem 3 & 7)
    add_res = client.post(f"/api/playlists/{playlist_id}/songs", json={"song_id": song_id})
    assert add_res.status_code == 200

    # Fetch playlist with songs
    get_p = client.get(f"/api/playlists/{playlist_id}")
    assert get_p.status_code == 200
    assert get_p.json()["song_count"] == 1
    assert get_p.json()["songs"][0]["id"] == song_id

    # Remove song from playlist
    rem_res = client.delete(f"/api/playlists/{playlist_id}/songs/{song_id}")
    assert rem_res.status_code == 200

    # Cleanup
    client.delete(f"/api/playlists/{playlist_id}")
    client.delete(f"/api/songs/{song_id}?delete_file=true")

def test_scanner_security_restriction():
    # Problem 2 & 8: Verify scanning Windows system folder is strictly blocked
    res = client.post("/api/scan", json={"directory_path": "C:\\Windows"})
    assert res.status_code == 200
    data = res.json()
    assert "error" in data
    assert "restricted" in data["error"].lower()
