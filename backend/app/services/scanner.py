import os
import uuid
import shutil
from pathlib import Path
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..config import settings
from ..models import Song, Artist, Album
from .metadata import extract_metadata

SUPPORTED_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"}

def scan_directory(source_dir: Path, db: Session, copy_to_storage: bool = False) -> Dict[str, Any]:
    """
    Scans a directory for audio files, extracts metadata and populates SQLite.
    If copy_to_storage is True, files are copied into the configured MUSIC_DIR.
    If False, files can be referenced directly or linked.
    """
    if not source_dir.exists() or not source_dir.is_dir():
        return {"error": f"Directory does not exist: {str(source_dir)}", "scanned": 0, "added": 0, "skipped": 0}

    scanned_count = 0
    added_count = 0
    skipped_count = 0

    for root, _, files in os.walk(source_dir):
        for f in files:
            file_path = Path(root) / f
            ext = file_path.suffix.lower()
            if ext not in SUPPORTED_EXTS:
                continue

            scanned_count += 1

            # Check if this file was already indexed by original filename & file size
            file_size = file_path.stat().st_size
            existing = db.query(Song).filter(
                Song.original_filename == f,
                Song.file_size == file_size
            ).first()

            if existing:
                skipped_count += 1
                continue

            # Handle storage location
            file_id = str(uuid.uuid4())
            if copy_to_storage:
                stored_filename = f"{file_id}{ext}"
                dest = settings.music_path / stored_filename
                try:
                    shutil.copy2(file_path, dest)
                except Exception:
                    continue
                audio_ref = stored_filename
            else:
                # Store absolute or relative path so zero-copy works
                audio_ref = str(file_path.resolve())

            # Extract metadata
            meta = extract_metadata(file_path)

            artist_name = meta["artist"] or "Unknown Artist"
            album_title = meta["album"] or "Unknown Album"
            song_title = meta["title"] or file_path.stem

            # Find or create artist
            artist_obj = db.query(Artist).filter(func.lower(Artist.name) == artist_name.lower()).first()
            if not artist_obj:
                artist_obj = Artist(name=artist_name)
                db.add(artist_obj)
                db.flush()

            # Find or create album
            album_obj = db.query(Album).filter(
                func.lower(Album.title) == album_title.lower(),
                Album.artist_id == artist_obj.id
            ).first()

            if not album_obj:
                album_obj = Album(
                    title=album_title,
                    artist_id=artist_obj.id,
                    artwork_path=meta["artwork_filename"],
                    year=meta["year"]
                )
                db.add(album_obj)
                db.flush()
            elif not album_obj.artwork_path and meta["artwork_filename"]:
                album_obj.artwork_path = meta["artwork_filename"]

            song = Song(
                id=file_id,
                title=song_title,
                artist_id=artist_obj.id,
                album_id=album_obj.id,
                audio_path=audio_ref,
                original_filename=f,
                duration_seconds=meta["duration_seconds"],
                genre=meta["genre"],
                file_size=meta["file_size"],
                bitrate=meta["bitrate"]
            )
            db.add(song)
            added_count += 1

    db.commit()

    return {
        "scanned": scanned_count,
        "added": added_count,
        "skipped": skipped_count
    }
