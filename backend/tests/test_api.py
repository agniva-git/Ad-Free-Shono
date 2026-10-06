import io
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["mode"] == "zero-cost-local-first"

def test_library_stats_initial():
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_songs" in data
    assert "total_artists" in data

def test_get_songs_empty():
    response = client.get("/api/songs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_playlist_lifecycle():
    # 1. Create playlist
    create_res = client.post("/api/playlists", json={
        "name": "My Roadtrip Jams",
        "description": "Chill roadtrip songs"
    })
    assert create_res.status_code == 201
    playlist = create_res.json()
    playlist_id = playlist["id"]
    assert playlist["name"] == "My Roadtrip Jams"

    # 2. Get playlist
    get_res = client.get(f"/api/playlists/{playlist_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == playlist_id

    # 3. Rename playlist
    patch_res = client.patch(f"/api/playlists/{playlist_id}", json={
        "name": "Updated Roadtrip Jams"
    })
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Updated Roadtrip Jams"

    # 4. Delete playlist
    del_res = client.delete(f"/api/playlists/{playlist_id}")
    assert del_res.status_code == 200

    # 5. Verify gone
    get_res_after = client.get(f"/api/playlists/{playlist_id}")
    assert get_res_after.status_code == 404

def test_upload_and_stream():
    # Create a small valid WAV-format binary in memory
    # 44-byte standard PCM WAV header + 100 bytes silence
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

    audio_file = io.BytesIO(wav_header)

    upload_res = client.post(
        "/api/upload",
        files={"file": ("test_track.wav", audio_file, "audio/wav")},
        data={"title": "Test Symphony", "artist": "Zero Cost Composer", "album": "Blueprint Debut"}
    )
    assert upload_res.status_code == 201
    song = upload_res.json()
    song_id = song["id"]
    assert song["title"] == "Test Symphony"
    assert song["artist_name"] == "Zero Cost Composer"

    # Test HTTP Range Streaming
    stream_res = client.get(
        f"/api/songs/{song_id}/stream",
        headers={"Range": "bytes=0-49"}
    )
    assert stream_res.status_code == 206
    assert "Content-Range" in stream_res.headers
    assert stream_res.headers["Content-Range"].startswith("bytes 0-49/")
    assert len(stream_res.content) == 50

    # Test Toggle Favorite
    fav_res = client.post(f"/api/songs/{song_id}/favorite")
    assert fav_res.status_code == 200
    assert fav_res.json()["is_favorite"] is True

    # Test Play History
    hist_res = client.post(f"/api/songs/{song_id}/history")
    assert hist_res.status_code == 200

    # Clean up song
    del_res = client.delete(f"/api/songs/{song_id}?delete_file=true")
    assert del_res.status_code == 200
