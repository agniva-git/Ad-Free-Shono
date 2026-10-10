from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import Song, User
from .security import user_from_request


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the admin can do this")
    return user


def can_edit_song(song: Song, user: User) -> bool:
    """Admins can change any song; everyone else only the songs they uploaded."""
    return user.role == "admin" or (song.uploaded_by is not None and song.uploaded_by == user.id)


def ensure_can_edit(song: Song, user: User) -> None:
    if not can_edit_song(song, user):
        raise HTTPException(status_code=403, detail="You can only change songs you uploaded")
