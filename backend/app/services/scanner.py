import os
import uuid
import hashlib
import shutil
from pathlib import Path
from typing import Dict, Any, Set
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..config import settings
from ..models import Song, Artist, Album
from .metadata import extract_metadata

SUPPORTED_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"}

FORBIDDEN_ROOTS = {"C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)", "C:\\System Volume Information"}

def is_safe_directory(path: Path) -> bool:
    """Blocks sensitive OS system paths from being scanned."""
    try:
        resolved = str(path.resolve()).lower()
        for forbidden in FORBIDDEN_ROOTS:
            if resolved.startswith(forbidden.lower()):
                return False
        # Do not allow scanning raw drive root directly (e.g. C:\)
        if len(resolved.rstrip("\\/")) <= 3:
            return False
        return True
    except Exception:
        return False

def compute_fast_file_signature(file_path: Path) -> str:
    """Computes a deterministic hash based on file size and first 64KB for instant duplicate matching."""
    try:
        stat = file_path.stat()
        file_size = stat.st_size
        hasher = hashlib.sha256()
        hasher.update(str(file_size).encode())
        with open(file_path, "rb") as f:
            chunk = f.read(65536)
            hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return f"{file_path.name}_{file_path.stat().st_size}"

def scan_directory(source_dir: Path, db: Session, copy_to_storage: bool = False) -> Dict[str, Any]:
    """
    Scans a directory for audio files, extracts metadata and populates SQLite.
    Includes security checks and robust duplicate detection.
    """
    if not source_dir.exists() or not source_dir.is_dir():
        return {"error": f"Directory does not exist: {str(source_dir)}", "scanned": 0, "added": 0, "skipped": 0}

    if not is_safe_directory(source_dir):
        return {"error": "Scanning this system directory is restricted for security.", "scanned": 0, "added": 0, "skipped": 0}

    scanned_count = 0
    added_count = 0
    skipped_count = 0

    # Build cache of existing songs by audio_path and (filename, file_size)
    existing_paths: Set[str] = {s.audio_path for s in db.query(Song.audio_path).all()}
    existing_files: Set[tuple] = {(s.original_filename, s.file_size) for s in db.query(Song.original_filename, Song.file_size).all()}

    for root, _, files in os.walk(source_dir):
        for f in files:
            file_path = Path(root) / f
            ext = file_path.suffix.lower()
            if ext not in SUPPORTED_EXTS:
                continue

            scanned_count += 1
            file_size = file_path.stat().st_size
            resolved_str = str(file_path.resolve())

            # Check 1: Already indexed by path
            if resolved_str in existing_paths:
                skipped_count += 1
                continue

            # Check 2: Already indexed by original filename & file size
            if (f, file_size) in existing_files:
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
                # Store absolute path so zero-copy works
                audio_ref = resolved_str

            # Extract metadata
            meta = extract_metadata(file_path)

            artist_name = meta["artist"] or "Unknown Artist"
            album_title = meta["album"] or "Unknown Album"
            song_title = meta["title"] or file_path.stem

            # Find or create artist
            artist_obj = db.query(Artist).filter(func.lower(Artist.name) == artist_name.lower()).first()
            if not artist_obj:
                artist_obj = Artist(
                    name=artist_name,
                    artwork_path=meta["artwork_filename"] # Propagate artist artwork if available!
                )
                db.add(artist_obj)
                db.flush()
            elif not artist_obj.artwork_path and meta["artwork_filename"]:
                artist_obj.artwork_path = meta["artwork_filename"]

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
            existing_paths.add(audio_ref)
            existing_files.add((f, file_size))
            added_count += 1

    db.commit()

    return {
        "scanned": scanned_count,
        "added": added_count,
        "skipped": skipped_count
    }
