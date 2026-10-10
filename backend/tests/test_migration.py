"""A database made before accounts existed must upgrade in place without losing anything."""
import sqlite3

OLD_SCHEMA = """
CREATE TABLE artists (id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE, artwork_path VARCHAR(500), created_at DATETIME);
CREATE TABLE albums (id VARCHAR(36) PRIMARY KEY, title VARCHAR(255) NOT NULL, artist_id VARCHAR(36) REFERENCES artists(id) ON DELETE SET NULL,
    artwork_path VARCHAR(500), year INTEGER, created_at DATETIME);
CREATE TABLE songs (id VARCHAR(36) PRIMARY KEY, title VARCHAR(255) NOT NULL, artist_id VARCHAR(36), album_id VARCHAR(36),
    audio_path VARCHAR(500) NOT NULL, original_filename VARCHAR(255), duration_seconds FLOAT, genre VARCHAR(100),
    file_size INTEGER, bitrate INTEGER, created_at DATETIME);
CREATE TABLE playlists (id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL, description VARCHAR(500), created_at DATETIME, updated_at DATETIME);
CREATE TABLE playlist_songs (id INTEGER PRIMARY KEY AUTOINCREMENT, playlist_id VARCHAR(36) NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    song_id VARCHAR(36) NOT NULL REFERENCES songs(id) ON DELETE CASCADE, position INTEGER, UNIQUE (playlist_id, song_id));
CREATE TABLE favorites (id INTEGER PRIMARY KEY AUTOINCREMENT, song_id VARCHAR(36) NOT NULL UNIQUE REFERENCES songs(id) ON DELETE CASCADE, created_at DATETIME);
CREATE TABLE play_history (id INTEGER PRIMARY KEY AUTOINCREMENT, song_id VARCHAR(36) NOT NULL REFERENCES songs(id) ON DELETE CASCADE, played_at DATETIME);

INSERT INTO artists VALUES ('ar1', 'Old Artist', NULL, '2026-01-01 00:00:00');
INSERT INTO songs VALUES ('s1', 'Old Song', 'ar1', NULL, 'old.wav', 'old.wav', 12.0, NULL, 100, NULL, '2026-01-01 00:00:00');
INSERT INTO songs VALUES ('s2', 'Other Song', 'ar1', NULL, 'o2.wav', 'o2.wav', 12.0, NULL, 100, NULL, '2026-01-01 00:00:00');
INSERT INTO playlists VALUES ('p1', 'Old list', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00');
INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES ('p1', 's1', 1);
INSERT INTO favorites (song_id, created_at) VALUES ('s1', '2026-01-01 00:00:00');
INSERT INTO favorites (song_id, created_at) VALUES ('ghost-song', '2026-01-01 00:00:00');
INSERT INTO play_history (song_id, played_at) VALUES ('s1', '2026-01-02 00:00:00');
"""


def test_old_database_is_upgraded_and_old_data_goes_to_the_admin(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from backend.app.database import Base
    from backend.app.models import Favorite, PlayHistory, Playlist, Song, User
    from backend.app.config import settings
    from backend.app.services.accounts import assign_legacy_rows, bootstrap_admin
    from backend.app.services.migrate import migrate_schema

    db_file = tmp_path / "old.db"
    con = sqlite3.connect(db_file)
    con.executescript(OLD_SCHEMA)
    con.commit(); con.close()

    engine = create_engine(f"sqlite:///{db_file.as_posix()}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi, _):
        dbapi.execute("PRAGMA foreign_keys=ON")

    migrate_schema(engine)
    migrate_schema(engine)          # running it twice must be harmless
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "migration-admin-pass-1")
    db = sessionmaker(bind=engine)()
    admin = bootstrap_admin(db)
    assign_legacy_rows(db)

    assert db.query(Song).count() == 2
    assert all(s.uploaded_by is None for s in db.query(Song))            # old songs: admin-only to edit
    play = db.query(Playlist).one()
    assert play.name == "Old list" and play.user_id == admin.id
    favs = db.query(Favorite).all()
    assert len(favs) == 1 and favs[0].song_id == "s1" and favs[0].user_id == admin.id   # the ghost row was dropped
    assert db.query(PlayHistory).one().user_id == admin.id

    # favorites are now unique per (person, song), not per song
    other = User(username="friend", password_hash="x", role="member")
    db.add(other); db.flush()
    db.add(Favorite(song_id="s1", user_id=other.id))
    db.commit()
    assert db.query(Favorite).filter(Favorite.song_id == "s1").count() == 2
    db.close()
