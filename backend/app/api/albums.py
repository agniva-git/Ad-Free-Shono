from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..deps import get_current_user
from ..models import Album, Song, Artist, User
from ..schemas import AlbumResponse, SongResponse
from ..services.helpers import format_song_response

router = APIRouter(prefix="/albums", tags=["Albums"])

@router.get("", response_model=List[AlbumResponse])
def get_albums(db: Session = Depends(get_db)):
    albums_with_data = db.query(
        Album,
        Artist.name.label("artist_name"),
        func.count(Song.id).label("song_count")
    ).outerjoin(Artist, Album.artist_id == Artist.id)\
     .outerjoin(Song, Album.id == Song.album_id)\
     .group_by(Album.id)\
     .order_by(Album.title.asc())\
     .all()

    result = []
    for album, artist_name, count in albums_with_data:
        result.append(AlbumResponse(
            id=album.id,
            title=album.title,
            year=album.year,
            artist_id=album.artist_id,
            artist_name=artist_name or "Unknown Artist",
            artwork_path=f"/api/artwork/{album.artwork_path}" if album.artwork_path else None,
            created_at=album.created_at,
            song_count=count
        ))
    return result

@router.get("/{album_id}")
def get_album_detail(album_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    songs = db.query(Song).filter(Song.album_id == album_id).order_by(Song.title.asc()).all()
    artist_name = album.artist.name if album.artist else "Unknown Artist"

    return {
        "album": AlbumResponse(
            id=album.id,
            title=album.title,
            year=album.year,
            artist_id=album.artist_id,
            artist_name=artist_name,
            artwork_path=f"/api/artwork/{album.artwork_path}" if album.artwork_path else None,
            created_at=album.created_at,
            song_count=len(songs)
        ),
        "songs": [format_song_response(s, user) for s in songs]
    }
