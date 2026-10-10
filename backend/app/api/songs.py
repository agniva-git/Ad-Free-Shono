from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import func

from ..database import get_db
from ..deps import ensure_can_edit, get_current_user
from ..models import Song, Artist, Album, Favorite, PlayHistory, User
from ..schemas import SongResponse, SongUpdate
from ..services.streaming import send_file_range_response
from ..services.helpers import format_song_response
from ..services.library import internal_audio_path, locate_audio, prune_empty

router = APIRouter(prefix="/songs", tags=["Songs"])


def _song_query(db: Session):
    return db.query(Song).options(
        joinedload(Song.artist),
        joinedload(Song.album),
        selectinload(Song.favorites),
    )


@router.get("", response_model=List[SongResponse])
def get_songs(
    search: Optional[str] = None,
    artist_id: Optional[str] = None,
    album_id: Optional[str] = None,
    favorites_only: bool = False,
    sort_by: str = "title",
    order: str = "asc",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = _song_query(db)

    if favorites_only:  # only this person's own likes
        query = query.join(Favorite, (Song.id == Favorite.song_id) & (Favorite.user_id == user.id))

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

    if sort_by == "created_at":
        sort_col = Song.created_at
    elif sort_by == "duration":
        sort_col = Song.duration_seconds
    else:
        sort_col = Song.title

    query = query.order_by(sort_col.desc() if order.lower() == "desc" else sort_col.asc())
    return [format_song_response(s, user) for s in query.all()]


@router.get("/history/recent", response_model=List[SongResponse])
def get_recently_played(limit: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # This person's own most recently played distinct songs
    recent_entries = db.query(
        PlayHistory.song_id,
        func.max(PlayHistory.played_at).label("latest_played")
    ).filter(PlayHistory.user_id == user.id)\
     .group_by(PlayHistory.song_id)\
     .order_by(func.max(PlayHistory.played_at).desc())\
     .limit(limit)\
     .all()

    if not recent_entries:
        return []

    song_ids = [entry[0] for entry in recent_entries]
    songs = _song_query(db).filter(Song.id.in_(song_ids)).all()

    song_map = {s.id: s for s in songs}
    return [format_song_response(song_map[sid], user) for sid in song_ids if sid in song_map]


@router.get("/{song_id}", response_model=SongResponse)
def get_song(song_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    song = _song_query(db).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return format_song_response(song, user)


@router.patch("/{song_id}", response_model=SongResponse)
def update_song(song_id: str, updates: SongUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    ensure_can_edit(song, user)

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
    prune_empty(db)  # the song may have left an artist/album with nothing in it
    song = _song_query(db).filter(Song.id == song_id).first()
    return format_song_response(song, user)


@router.delete("/{song_id}")
def delete_song(song_id: str, delete_file: bool = True, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    ensure_can_edit(song, user)

    # Only files inside the app's own storage may be removed. Scanned (zero-copy)
    # songs point at the owner's own folders, so those files are always left alone.
    owned_file = internal_audio_path(song.audio_path) if (delete_file and song.audio_path) else None

    db.delete(song)
    db.commit()

    file_deleted = False
    if owned_file and owned_file.is_file():
        try:
            owned_file.unlink()
            file_deleted = True
        except OSError:
            pass

    prune_empty(db)
    return {"message": "Song deleted successfully", "id": song_id, "file_deleted": file_deleted}


@router.get("/{song_id}/stream")
def stream_song(song_id: str, range: Optional[str] = Header(None), db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    file_path = locate_audio(song.audio_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")

    return send_file_range_response(file_path, range)


@router.post("/{song_id}/favorite")
def toggle_favorite(song_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    fav = db.query(Favorite).filter(Favorite.song_id == song_id, Favorite.user_id == user.id).first()
    if fav:
        db.delete(fav)
        db.commit()
        return {"song_id": song_id, "is_favorite": False}

    db.add(Favorite(song_id=song_id, user_id=user.id))
    db.commit()
    return {"song_id": song_id, "is_favorite": True}


@router.post("/{song_id}/history")
def record_history(song_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    db.add(PlayHistory(song_id=song_id, user_id=user.id, played_at=datetime.now(timezone.utc)))
    db.commit()
    return {"message": "Recorded playback history"}
