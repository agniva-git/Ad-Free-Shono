from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from ..database import get_db
from ..models import Song, Artist, Album, Favorite, PlayHistory
from ..schemas import SongResponse, SongUpdate
from ..services.streaming import send_file_range_response
from ..services.helpers import format_song_response
from ..config import settings

router = APIRouter(prefix="/songs", tags=["Songs"])

@router.get("", response_model=List[SongResponse])
def get_songs(
    search: Optional[str] = None,
    artist_id: Optional[str] = None,
    album_id: Optional[str] = None,
    favorites_only: bool = False,
    sort_by: str = "title",
    order: str = "asc",
    db: Session = Depends(get_db)
):
    query = db.query(Song).options(
        joinedload(Song.artist),
        joinedload(Song.album),
        joinedload(Song.favorite_entry)
    )

    if favorites_only:
        query = query.join(Favorite, Song.id == Favorite.song_id)

    if artist_id:
        query = query.filter(Song.artist_id == artist_id)

    if album_id:
        query = query.filter(Song.album_id == album_id)

    if search:
        search_filter = f"%{search.strip()}%"
        query = query.outerjoin(Artist, Song.artist_id == Artist.id).outerjoin(Album, Song.album_id == Album.id).filter(
            (Song.title.ilike(search_filter)) |
            (Artist.name.ilike(search_filter)) |
            (Album.title.ilike(search_filter))
        )

    # Sorting
    if sort_by == "created_at":
        sort_col = Song.created_at
    elif sort_by == "duration":
        sort_col = Song.duration_seconds
    else:
        sort_col = Song.title

    if order.lower() == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    songs = query.all()
    return [format_song_response(s) for s in songs]

@router.get("/{song_id}", response_model=SongResponse)
def get_song(song_id: str, db: Session = Depends(get_db)):
    song = db.query(Song).options(
        joinedload(Song.artist),
        joinedload(Song.album),
        joinedload(Song.favorite_entry)
    ).filter(Song.id == song_id).first()

    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return format_song_response(song)

@router.patch("/{song_id}", response_model=SongResponse)
def update_song(song_id: str, updates: SongUpdate, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    if updates.title is not None and updates.title.strip():
        song.title = updates.title.strip()

    if updates.genre is not None:
        song.genre = updates.genre.strip() or None

    if updates.artist_name is not None:
        artist_name = updates.artist_name.strip()
        if artist_name:
            artist = db.query(Artist).filter(func.lower(Artist.name) == artist_name.lower()).first()
            if not artist:
                artist = Artist(name=artist_name)
                db.add(artist)
                db.flush()
            song.artist_id = artist.id
        else:
            song.artist_id = None

    if updates.album_title is not None:
        album_title = updates.album_title.strip()
        if album_title:
            album = db.query(Album).filter(
                func.lower(Album.title) == album_title.lower(),
                Album.artist_id == song.artist_id
            ).first()
            if not album:
                album = Album(title=album_title, artist_id=song.artist_id)
                db.add(album)
                db.flush()
            song.album_id = album.id
        else:
            song.album_id = None

    db.commit()
    db.refresh(song)
    return format_song_response(song)

@router.delete("/{song_id}")
def delete_song(song_id: str, delete_file: bool = True, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    # Optionally delete physical audio file
    if delete_file and song.audio_path:
        file_path = settings.music_path / song.audio_path
        if file_path.exists() and file_path.is_file():
            try:
                file_path.unlink()
            except Exception:
                pass

    db.delete(song)
    db.commit()
    return {"message": "Song deleted successfully", "id": song_id}

@router.get("/{song_id}/stream")
def stream_song(song_id: str, range: Optional[str] = Header(None), db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    file_path = settings.music_path / song.audio_path
    if not file_path.exists():
        # Check absolute or relative fallback
        alt_path = Path(song.audio_path)
        if alt_path.exists():
            file_path = alt_path
        else:
            raise HTTPException(status_code=404, detail="Audio file missing on disk")

    return send_file_range_response(file_path, range)

@router.post("/{song_id}/favorite")
def toggle_favorite(song_id: str, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    fav = db.query(Favorite).filter(Favorite.song_id == song_id).first()
    if fav:
        db.delete(fav)
        db.commit()
        return {"song_id": song_id, "is_favorite": False}
    else:
        new_fav = Favorite(song_id=song_id)
        db.add(new_fav)
        db.commit()
        return {"song_id": song_id, "is_favorite": True}

@router.get("/history/recent", response_model=List[SongResponse])
def get_recently_played(limit: int = 20, db: Session = Depends(get_db)):
    # Fetch most recently played distinct songs
    recent_entries = db.query(
        PlayHistory.song_id,
        func.max(PlayHistory.played_at).label("latest_played")
    ).group_by(PlayHistory.song_id)\
     .order_by(func.max(PlayHistory.played_at).desc())\
     .limit(limit)\
     .all()

    if not recent_entries:
        return []

    song_ids = [entry[0] for entry in recent_entries]
    songs = db.query(Song).options(
        joinedload(Song.artist),
        joinedload(Song.album),
        joinedload(Song.favorite_entry)
    ).filter(Song.id.in_(song_ids)).all()

    # Preserve recent playback order
    song_map = {s.id: s for s in songs}
    ordered_songs = [song_map[sid] for sid in song_ids if sid in song_map]
    return [format_song_response(s) for s in ordered_songs]

@router.post("/{song_id}/history")
def record_history(song_id: str, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    entry = PlayHistory(song_id=song_id, played_at=datetime.now(timezone.utc))
    db.add(entry)
    db.commit()
    return {"message": "Recorded playback history"}
