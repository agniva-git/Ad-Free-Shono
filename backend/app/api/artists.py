from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from ..database import get_db
from ..models import Artist, Song
from ..schemas import ArtistResponse, SongResponse
from ..security import get_current_user
from ..services.helpers import format_song_response

router = APIRouter(prefix="/artists", tags=["Artists"])

@router.get("", response_model=List[ArtistResponse])
def get_artists(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    artists_with_counts = db.query(
        Artist,
        func.count(Song.id).label("song_count")
    ).outerjoin(Song, Artist.id == Song.artist_id)\
     .group_by(Artist.id)\
     .order_by(Artist.name.asc())\
     .all()

    result = []
    for artist, count in artists_with_counts:
        result.append(ArtistResponse(
            id=artist.id,
            name=artist.name,
            artwork_path=f"/api/artwork/{artist.artwork_path}" if artist.artwork_path else None,
            created_at=artist.created_at,
            song_count=count
        ))
    return result

@router.get("/{artist_id}")
def get_artist_detail(artist_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    songs = db.query(Song).options(
        joinedload(Song.artist), joinedload(Song.album), joinedload(Song.favorite_entries)
    ).filter(Song.artist_id == artist_id).order_by(Song.title.asc()).all()
    return {
        "artist": ArtistResponse(
            id=artist.id,
            name=artist.name,
            artwork_path=f"/api/artwork/{artist.artwork_path}" if artist.artwork_path else None,
            created_at=artist.created_at,
            song_count=len(songs)
        ),
        "songs": [format_song_response(s, user_id=current_user.id) for s in songs]
    }
