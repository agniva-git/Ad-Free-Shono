from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Song, Artist, Album
from ..schemas import SongResponse, ArtistResponse, AlbumResponse
from ..services.helpers import format_song_response

router = APIRouter(prefix="/search", tags=["Search"])

@router.get("")
def search_all(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    term = f"%{q.strip()}%"

    # Search songs by title, artist name, and album title
    songs = db.query(Song).options(
        joinedload(Song.artist),
        joinedload(Song.album),
        joinedload(Song.favorite_entry)
    ).outerjoin(Artist, Song.artist_id == Artist.id)\
     .outerjoin(Album, Song.album_id == Album.id)\
     .filter(
        (Song.title.ilike(term)) |
        (Artist.name.ilike(term)) |
        (Album.title.ilike(term))
    ).limit(30).all()

    # Search artists
    artists = db.query(Artist).filter(Artist.name.ilike(term)).limit(12).all()

    # Search albums
    albums = db.query(Album).options(
        joinedload(Album.artist),
        joinedload(Album.songs)
    ).outerjoin(Artist, Album.artist_id == Artist.id)\
     .filter(
        (Album.title.ilike(term)) |
        (Artist.name.ilike(term))
    ).limit(12).all()

    return {
        "query": q,
        "songs": [format_song_response(s) for s in songs],
        "artists": [
            ArtistResponse(
                id=a.id,
                name=a.name,
                artwork_path=f"/api/artwork/{a.artwork_path}" if a.artwork_path else None,
                created_at=a.created_at,
                song_count=len(a.songs)
            ) for a in artists
        ],
        "albums": [
            AlbumResponse(
                id=al.id,
                title=al.title,
                year=al.year,
                artist_id=al.artist_id,
                artist_name=al.artist.name if al.artist else "Unknown Artist",
                artwork_path=f"/api/artwork/{al.artwork_path}" if al.artwork_path else None,
                created_at=al.created_at,
                song_count=len(al.songs)
            ) for al in albums
        ]
    }
