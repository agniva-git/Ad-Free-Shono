from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import Song, Artist, Album, Playlist
from ..schemas import LibraryStats
from ..security import get_current_user

router = APIRouter(prefix="/stats", tags=["Stats"])

@router.get("", response_model=LibraryStats)
def get_library_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    total_songs = db.query(func.count(Song.id)).scalar() or 0
    total_artists = db.query(func.count(Artist.id)).scalar() or 0
    total_albums = db.query(func.count(Album.id)).scalar() or 0
    # only count THIS user's playlists
    total_playlists = db.query(func.count(Playlist.id)).filter(
        Playlist.user_id == current_user.id
    ).scalar() or 0
    total_duration = db.query(func.sum(Song.duration_seconds)).scalar() or 0.0

    return LibraryStats(
        total_songs=total_songs,
        total_artists=total_artists,
        total_albums=total_albums,
        total_playlists=total_playlists,
        total_duration_seconds=round(float(total_duration), 2)
    )
