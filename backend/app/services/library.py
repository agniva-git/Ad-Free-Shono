from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Album, Artist, Favorite, PlayHistory, PlaylistSong, Song


def locate_audio(audio_path: str) -> Path:
    """Where a song's file lives. Stored paths are either relative to MUSIC_DIR
    (uploads / copied scans) or absolute (zero-copy scans)."""
    p = Path(audio_path)
    return p if p.is_absolute() else settings.music_path / p


def internal_audio_path(audio_path: str) -> Optional[Path]:
    """Return the file path only if it is inside the app's own MUSIC_DIR, else None.
    Files outside MUSIC_DIR belong to the user and must never be deleted by this app."""
    base = settings.music_path.resolve()
    candidate = locate_audio(audio_path).resolve()
    return candidate if candidate.is_relative_to(base) else None


def _artwork_in_use(db: Session, filename: str) -> bool:
    return bool(
        db.query(Album.id).filter(Album.artwork_path == filename).first()
        or db.query(Artist.id).filter(Artist.artwork_path == filename).first()
    )


def prune_empty(db: Session) -> dict:
    """Remove rows that point at nothing: history/favorites/playlist entries for missing
    songs, albums and artists with no songs, and artwork files nobody references."""
    song_ids = db.query(Song.id)

    db.query(PlayHistory).filter(~PlayHistory.song_id.in_(song_ids)).delete(synchronize_session=False)
    db.query(Favorite).filter(~Favorite.song_id.in_(song_ids)).delete(synchronize_session=False)
    db.query(PlaylistSong).filter(~PlaylistSong.song_id.in_(song_ids)).delete(synchronize_session=False)

    artwork_candidates = set()

    used_albums = db.query(Song.album_id).filter(Song.album_id.isnot(None))
    empty_albums = db.query(Album).filter(~Album.id.in_(used_albums)).all()
    for album in empty_albums:
        if album.artwork_path:
            artwork_candidates.add(album.artwork_path)
        db.delete(album)
    db.flush()

    used_by_songs = db.query(Song.artist_id).filter(Song.artist_id.isnot(None))
    used_by_albums = db.query(Album.artist_id).filter(Album.artist_id.isnot(None))
    empty_artists = db.query(Artist).filter(
        ~Artist.id.in_(used_by_songs), ~Artist.id.in_(used_by_albums)
    ).all()
    for artist in empty_artists:
        if artist.artwork_path:
            artwork_candidates.add(artist.artwork_path)
        db.delete(artist)
    db.flush()

    removed_files = 0
    for name in artwork_candidates:
        if not _artwork_in_use(db, name):
            (settings.artwork_path / name).unlink(missing_ok=True)
            removed_files += 1

    db.commit()
    return {
        "albums_removed": len(empty_albums),
        "artists_removed": len(empty_artists),
        "artwork_removed": removed_files,
    }


def sweep_unused_artwork(db: Session) -> int:
    """Startup-only: delete artwork files no album/artist references (old duplicates)."""
    referenced = {r[0] for r in db.query(Album.artwork_path).filter(Album.artwork_path.isnot(None))}
    referenced |= {r[0] for r in db.query(Artist.artwork_path).filter(Artist.artwork_path.isnot(None))}
    removed = 0
    for f in settings.artwork_path.iterdir():
        if f.is_file() and f.name not in referenced:
            f.unlink(missing_ok=True)
            removed += 1
    return removed
