from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from ..database import get_db
from ..models import Playlist, PlaylistSong, Song, User
from ..schemas import PlaylistCreate, PlaylistUpdate, PlaylistResponse, PlaylistAddSong
from ..security import get_current_user
from ..services.helpers import format_song_response

router = APIRouter(prefix="/playlists", tags=["Playlists"])


@router.get("", response_model=List[PlaylistResponse])
def get_playlists(db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """Return only the current user's playlists."""
    playlists = (
        db.query(Playlist)
        .filter(Playlist.user_id == current_user.id)
        .order_by(Playlist.updated_at.desc())
        .all()
    )
    result = []
    for p in playlists:
        song_count = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == p.id).count()
        result.append(PlaylistResponse(
            id=p.id, name=p.name, description=p.description,
            created_at=p.created_at, updated_at=p.updated_at,
            song_count=song_count, songs=[]
        ))
    return result


@router.post("", response_model=PlaylistResponse, status_code=status.HTTP_201_CREATED)
def create_playlist(payload: PlaylistCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Playlist name cannot be empty")

    playlist = Playlist(
        user_id=current_user.id,
        name=payload.name.strip(),
        description=payload.description,
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)

    return PlaylistResponse(
        id=playlist.id, name=playlist.name, description=playlist.description,
        created_at=playlist.created_at, updated_at=playlist.updated_at,
        song_count=0, songs=[]
    )


@router.get("/{playlist_id}", response_model=PlaylistResponse)
def get_playlist(playlist_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == current_user.id,
    ).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    items = db.query(PlaylistSong).options(
        joinedload(PlaylistSong.song).joinedload(Song.artist),
        joinedload(PlaylistSong.song).joinedload(Song.album),
        joinedload(PlaylistSong.song).joinedload(Song.favorite_entries),
    ).filter(PlaylistSong.playlist_id == playlist_id).order_by(PlaylistSong.position.asc()).all()

    songs = [format_song_response(item.song, user_id=current_user.id) for item in items if item.song]

    return PlaylistResponse(
        id=playlist.id, name=playlist.name, description=playlist.description,
        created_at=playlist.created_at, updated_at=playlist.updated_at,
        song_count=len(songs), songs=songs,
    )


@router.patch("/{playlist_id}", response_model=PlaylistResponse)
def update_playlist(playlist_id: str, payload: PlaylistUpdate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == current_user.id,
    ).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    if payload.name is not None and payload.name.strip():
        playlist.name = payload.name.strip()
    if payload.description is not None:
        playlist.description = payload.description.strip()

    db.commit()
    db.refresh(playlist)
    return get_playlist(playlist_id, db, current_user)


@router.delete("/{playlist_id}")
def delete_playlist(playlist_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == current_user.id,
    ).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    db.delete(playlist)
    db.commit()
    return {"message": "Playlist deleted successfully", "id": playlist_id}


@router.post("/{playlist_id}/songs")
def add_song_to_playlist(playlist_id: str, payload: PlaylistAddSong,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == current_user.id,
    ).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    song = db.query(Song).filter(Song.id == payload.song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    existing = db.query(PlaylistSong).filter(
        PlaylistSong.playlist_id == playlist_id,
        PlaylistSong.song_id == payload.song_id
    ).first()
    if existing:
        return {"message": "Song already in playlist"}

    max_pos = db.query(func.max(PlaylistSong.position)).filter(
        PlaylistSong.playlist_id == playlist_id
    ).scalar() or 0

    entry = PlaylistSong(playlist_id=playlist_id, song_id=payload.song_id, position=max_pos + 1)
    db.add(entry)
    db.commit()
    return {"message": "Song added to playlist"}


@router.delete("/{playlist_id}/songs/{song_id}")
def remove_song_from_playlist(playlist_id: str, song_id: str,
                               db: Session = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    # Confirm the user owns this playlist
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == current_user.id,
    ).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    entry = db.query(PlaylistSong).filter(
        PlaylistSong.playlist_id == playlist_id,
        PlaylistSong.song_id == song_id
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Song not in playlist")

    db.delete(entry)
    db.commit()
    return {"message": "Song removed from playlist"}
