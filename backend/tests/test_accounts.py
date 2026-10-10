"""Multiple people: one shared library, private playlists/likes/history, per-person permissions."""
import pytest

from conftest import ADMIN_PW, USER_PW
from helpers import make_wav, upload


# ---------- the shared library ----------

def test_everyone_sees_everyones_uploads(make_client):
    a, b = make_client("alice"), make_client("bob")
    for i in range(10):
        upload(a, f"a{i}.wav", tone=i + 1, title=f"A song {i}")
    for i in range(7):
        upload(b, f"b{i}.wav", tone=i + 100, title=f"B song {i}")

    admin = make_client("admin")
    for who in (a, b, admin):
        songs = who.get("/api/songs").json()
        assert len(songs) == 17
        assert who.get("/api/stats").json()["total_songs"] == 17


def test_same_file_is_only_kept_once(make_client, app_modules):
    *_, settings = app_modules
    a, b = make_client("alice"), make_client("bob")
    upload(a, "one.wav", tone=5, title="Shared")
    res = b.post("/api/upload", files={"file": ("copy.wav", make_wav(tone=5), "audio/wav")})
    assert res.status_code == 409 and "Already in the library" in res.json()["detail"]
    assert len(a.get("/api/songs").json()) == 1
    assert len(list(settings.music_path.iterdir())) == 1  # the rejected copy left no file behind


# ---------- private playlists ----------

def test_playlists_are_private(make_client):
    a, b, admin = make_client("alice"), make_client("bob"), make_client("admin")
    song = upload(a, tone=3, title="Song")["id"]

    pid = a.post("/api/playlists", json={"name": "Alice only"}).json()["id"]
    assert a.post(f"/api/playlists/{pid}/songs", json={"song_id": song}).status_code == 200

    assert [p["name"] for p in a.get("/api/playlists").json()] == ["Alice only"]
    for other in (b, admin):  # not even the admin can see someone's playlist
        assert other.get("/api/playlists").json() == []
        assert other.get(f"/api/playlists/{pid}").status_code == 404
        assert other.patch(f"/api/playlists/{pid}", json={"name": "hijacked"}).status_code == 404
        assert other.post(f"/api/playlists/{pid}/songs", json={"song_id": song}).status_code == 404
        assert other.delete(f"/api/playlists/{pid}/songs/{song}").status_code == 404
        assert other.delete(f"/api/playlists/{pid}").status_code == 404

    # still intact for the owner
    assert a.get(f"/api/playlists/{pid}").json()["song_count"] == 1
    assert b.get("/api/stats").json()["total_playlists"] == 0
    assert a.get("/api/stats").json()["total_playlists"] == 1


def test_two_people_can_use_the_same_playlist_name(make_client):
    a, b = make_client("alice"), make_client("bob")
    a.post("/api/playlists", json={"name": "Road trip"})
    b.post("/api/playlists", json={"name": "Road trip"})
    assert len(a.get("/api/playlists").json()) == 1
    assert len(b.get("/api/playlists").json()) == 1


# ---------- private likes and history ----------

def test_likes_and_history_are_per_person(make_client):
    a, b = make_client("alice"), make_client("bob")
    sid = upload(a, tone=9, title="Hit")["id"]

    a.post(f"/api/songs/{sid}/favorite")
    a.post(f"/api/songs/{sid}/history")

    assert a.get("/api/songs").json()[0]["is_favorite"] is True
    assert b.get("/api/songs").json()[0]["is_favorite"] is False
    assert len(a.get("/api/songs?favorites_only=true").json()) == 1
    assert b.get("/api/songs?favorites_only=true").json() == []
    assert len(a.get("/api/songs/history/recent").json()) == 1
    assert b.get("/api/songs/history/recent").json() == []

    # bob liking it does not undo alice's like
    assert b.post(f"/api/songs/{sid}/favorite").json()["is_favorite"] is True
    assert a.get("/api/songs").json()[0]["is_favorite"] is True


# ---------- who may change what ----------

def test_only_the_owner_or_admin_can_edit_or_delete_a_song(make_client):
    a, b, admin = make_client("alice"), make_client("bob"), make_client("admin")
    sid = upload(a, tone=11, title="Alice's")["id"]

    assert a.get(f"/api/songs/{sid}").json()["can_edit"] is True
    assert b.get(f"/api/songs/{sid}").json()["can_edit"] is False
    assert admin.get(f"/api/songs/{sid}").json()["can_edit"] is True

    assert b.patch(f"/api/songs/{sid}", json={"title": "mine now"}).status_code == 403
    assert b.delete(f"/api/songs/{sid}").status_code == 403
    assert a.get(f"/api/songs/{sid}").json()["title"] == "Alice's"

    assert a.patch(f"/api/songs/{sid}", json={"title": "Renamed"}).status_code == 200
    assert admin.patch(f"/api/songs/{sid}", json={"title": "Admin edit"}).status_code == 200
    assert a.delete(f"/api/songs/{sid}").status_code == 200


def test_deleting_a_song_removes_it_for_everyone(make_client):
    a, b = make_client("alice"), make_client("bob")
    sid = upload(a, tone=12, title="Gone soon")["id"]
    pid = b.post("/api/playlists", json={"name": "Bob list"}).json()["id"]
    b.post(f"/api/playlists/{pid}/songs", json={"song_id": sid})
    b.post(f"/api/songs/{sid}/favorite")

    a.delete(f"/api/songs/{sid}")
    assert b.get("/api/songs").json() == []
    assert b.get(f"/api/playlists/{pid}").json()["song_count"] == 0
    assert b.get("/api/songs?favorites_only=true").json() == []


def test_friends_cannot_scan_or_manage_users(make_client):
    b = make_client("bob")
    assert b.post("/api/scan", json={"directory_path": "/tmp"}).status_code == 403
    assert b.get("/api/admin/users").status_code == 403
    assert b.post("/api/admin/users", json={"username": "x" * 5, "password": USER_PW}).status_code == 403


def test_scanned_songs_belong_to_the_admin(make_client, tmp_path):
    admin, b = make_client("admin"), make_client("bob")
    folder = tmp_path / "Music"
    folder.mkdir()
    (folder / "s.wav").write_bytes(make_wav(tone=40).getvalue())
    assert admin.post("/api/scan", json={"directory_path": str(folder)}).json()["added"] == 1
    song = b.get("/api/songs").json()[0]
    assert song["can_edit"] is False
    assert b.delete(f"/api/songs/{song['id']}").status_code == 403


# ---------- upload allowance ----------

def test_friend_upload_allowance_but_admin_unlimited(make_client, app_modules, monkeypatch):
    *_, settings = app_modules
    monkeypatch.setattr(settings, "MEMBER_QUOTA_MB", 0)
    b, admin = make_client("bob"), make_client("admin")

    res = b.post("/api/upload", files={"file": ("x.wav", make_wav(tone=60), "audio/wav")})
    assert res.status_code == 413 and "Upload limit reached" in res.json()["detail"]
    assert list(settings.music_path.iterdir()) == []

    assert admin.post("/api/upload", files={"file": ("y.wav", make_wav(tone=61), "audio/wav")}).status_code == 201


# ---------- account management (admin) ----------

def test_admin_creates_a_friend_who_can_then_log_in(make_client, anon):
    admin = make_client("admin")
    res = admin.post("/api/admin/users", json={"username": "Carol", "password": USER_PW})
    assert res.status_code == 201 and res.json()["username"] == "carol" and res.json()["role"] == "member"

    ok = anon.post("/api/login", json={"username": "CAROL", "password": USER_PW})  # case-insensitive name
    assert ok.status_code == 200 and ok.json()["user"]["username"] == "carol"
    assert anon.get("/api/songs").status_code == 200


@pytest.mark.parametrize("payload,status", [
    ({"username": "ab", "password": USER_PW}, 400),                    # name too short
    ({"username": "bad name!", "password": USER_PW}, 400),             # illegal characters
    ({"username": "dave", "password": "short"}, 400),                  # password too short
    ({"username": "dave", "password": "change-me-please"}, 400),       # placeholder password
    ({"username": "dave", "password": "dave"}, 400),                   # same as the username
    ({"username": "dave", "password": USER_PW, "role": "owner"}, 400), # unknown role
])
def test_creating_a_user_validates_input(make_client, payload, status):
    assert make_client("admin").post("/api/admin/users", json=payload).status_code == status


def test_duplicate_usernames_are_refused(make_client):
    admin = make_client("admin")
    assert admin.post("/api/admin/users", json={"username": "erin", "password": USER_PW}).status_code == 201
    assert admin.post("/api/admin/users", json={"username": "ERIN", "password": USER_PW}).status_code == 409


def test_disabling_a_friend_locks_them_out_immediately(make_client, anon):
    admin, b = make_client("admin"), make_client("bob")
    bob_id = next(u["id"] for u in admin.get("/api/admin/users").json() if u["username"] == "bob")
    assert b.get("/api/songs").status_code == 200

    assert admin.patch(f"/api/admin/users/{bob_id}", json={"is_active": False}).status_code == 200
    assert b.get("/api/songs").status_code == 401                       # the open session dies
    assert anon.post("/api/login", json={"username": "bob", "password": USER_PW}).status_code == 401

    admin.patch(f"/api/admin/users/{bob_id}", json={"is_active": True})
    assert anon.post("/api/login", json={"username": "bob", "password": USER_PW}).status_code == 200


def test_admin_password_reset_signs_the_friend_out_everywhere(make_client, anon):
    admin, b = make_client("admin"), make_client("bob")
    bob_id = next(u["id"] for u in admin.get("/api/admin/users").json() if u["username"] == "bob")
    new_pw = "a-brand-new-password-9"

    assert admin.patch(f"/api/admin/users/{bob_id}", json={"password": "short"}).status_code == 400
    assert admin.patch(f"/api/admin/users/{bob_id}", json={"password": new_pw}).status_code == 200

    assert b.get("/api/songs").status_code == 401
    assert anon.post("/api/login", json={"username": "bob", "password": USER_PW}).status_code == 401
    assert anon.post("/api/login", json={"username": "bob", "password": new_pw}).status_code == 200


def test_admin_cannot_lock_themselves_or_the_last_admin_out(make_client):
    admin = make_client("admin")
    me = admin.get("/api/admin/users").json()[0]["id"]
    assert admin.patch(f"/api/admin/users/{me}", json={"is_active": False}).status_code == 400
    assert admin.patch(f"/api/admin/users/{me}", json={"role": "member"}).status_code == 400
    assert admin.get("/api/songs").status_code == 200


def test_a_second_admin_can_be_made_and_listing_shows_upload_counts(make_client):
    admin, b = make_client("admin"), make_client("bob")
    upload(b, tone=70, title="B1")
    users = {u["username"]: u for u in admin.get("/api/admin/users").json()}
    assert users["bob"]["upload_count"] == 1 and users["admin"]["upload_count"] == 0

    assert admin.patch(f"/api/admin/users/{users['bob']['id']}", json={"role": "admin"}).status_code == 200
    assert b.get("/api/admin/users").status_code == 200


def test_changing_own_password(make_client, anon):
    b = make_client("bob")
    other_device = make_client("bob")
    new_pw = "bobs-new-password-77"

    assert b.post("/api/me/password", json={"current_password": "wrong", "new_password": new_pw}).status_code == 403
    assert b.post("/api/me/password", json={"current_password": USER_PW, "new_password": "short"}).status_code == 400
    assert b.post("/api/me/password", json={"current_password": USER_PW, "new_password": new_pw}).status_code == 200

    assert b.get("/api/songs").status_code == 200              # this device stays signed in
    assert other_device.get("/api/songs").status_code == 401   # other devices are signed out
    assert anon.post("/api/login", json={"username": "bob", "password": new_pw}).status_code == 200
