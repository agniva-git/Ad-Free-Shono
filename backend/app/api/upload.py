import hashlib
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Album, Artist, Song, User
from ..schemas import SongResponse
from ..services.helpers import format_song_response
from ..services.metadata import extract_metadata

router = APIRouter(prefix="/upload", tags=["Upload"])

ALLOWED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"}
COPY_CHUNK = 1024 * 1024


# Plain "def" (not "async def"): the file copy is blocking, so FastAPI runs it in a
# worker thread instead of freezing the event loop while a big file uploads.
@router.post("", response_model=SongResponse, status_code=status.HTTP_201_CREATED)
def upload_audio(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    artist: Optional[str] = Form(None),
    album: Optional[str] = Form(None),
    genre: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    original_filename = file.filename or "unknown.mp3"
    ext = Path(original_filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    file_id = str(uuid.uuid4())
    stored_filename = f"{file_id}{ext}"
    dest_path = settings.music_path / stored_filename
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    # Friends have a total upload allowance; the admin is unlimited
    quota_left = None
    if user.role != "admin":
        used = db.query(func.coalesce(func.sum(Song.file_size), 0)).filter(Song.uploaded_by == user.id).scalar()
        quota_left = settings.MEMBER_QUOTA_MB * 1024 * 1024 - int(used)

    try:
        written = 0
        sha = hashlib.sha256()
        with open(dest_path, "wb") as buffer:
            while chunk := file.file.read(COPY_CHUNK):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File is larger than the {settings.MAX_UPLOAD_MB} MB limit",
                    )
                if quota_left is not None and written > quota_left:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload limit reached ({settings.MEMBER_QUOTA_MB} MB per account). Ask the admin for more space.",
                    )
                sha.update(chunk)
                buffer.write(chunk)

        # The library is shared, so the same file is only kept once
        digest = sha.hexdigest()
        twin = db.query(Song).filter(Song.file_hash == digest).first()
        if twin:
            raise HTTPException(
                status_code=409,
                detail=f"Already in the library as \"{twin.title}\".",
            )

        meta = extract_metadata(dest_path)

        final_title = title.strip() if (title and title.strip()) else meta["title"]
        final_artist = artist.strip() if (artist and artist.strip()) else meta["artist"]
        final_album = album.strip() if (album and album.strip()) else meta["album"]
        final_genre = genre.strip() if (genre and genre.strip()) else meta["genre"]

        artist_obj = db.query(Artist).filter(func.lower(Artist.name) == final_artist.lower()).first()
        if not artist_obj:
            artist_obj = Artist(name=final_artist)
            db.add(artist_obj)
            db.flush()

        album_obj = db.query(Album).filter(
            func.lower(Album.title) == final_album.lower(),
            Album.artist_id == artist_obj.id,
        ).first()
        if not album_obj:
            album_obj = Album(
                title=final_album,
                artist_id=artist_obj.id,
                artwork_path=meta["artwork_filename"],
                year=meta["year"],
            )
            db.add(album_obj)
            db.flush()
        elif not album_obj.artwork_path and meta["artwork_filename"]:
            album_obj.artwork_path = meta["artwork_filename"]

        song = Song(
            id=file_id,
            title=final_title,
            artist_id=artist_obj.id,
            album_id=album_obj.id,
            audio_path=stored_filename,
            original_filename=original_filename,
            duration_seconds=meta["duration_seconds"],
            genre=final_genre,
            file_size=meta["file_size"],
            bitrate=meta["bitrate"],
            uploaded_by=user.id,
            file_hash=digest,
        )
        db.add(song)
        db.commit()
        db.refresh(song)
    except BaseException:
        # Never leave a half-written file or a half-finished DB transaction behind
        db.rollback()
        dest_path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()

    return format_song_response(song, user)
