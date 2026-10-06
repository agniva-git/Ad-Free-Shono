import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
import mutagen
from mutagen.id3 import ID3, APIC
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover
from ..config import settings

def extract_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extracts metadata and embedded cover art from an audio file.
    Supports MP3, FLAC, M4A, OGG.
    """
    metadata: Dict[str, Any] = {
        "title": file_path.stem,
        "artist": "Unknown Artist",
        "album": "Unknown Album",
        "genre": None,
        "year": None,
        "duration_seconds": 0.0,
        "bitrate": None,
        "artwork_filename": None,
        "file_size": file_path.stat().st_size if file_path.exists() else 0
    }

    try:
        audio = mutagen.File(str(file_path), easy=False)
        if audio is None:
            return metadata

        # Duration & Bitrate
        if hasattr(audio, "info") and audio.info:
            metadata["duration_seconds"] = round(float(getattr(audio.info, "length", 0.0)), 2)
            metadata["bitrate"] = getattr(audio.info, "bitrate", None)
            if metadata["bitrate"]:
                metadata["bitrate"] = int(metadata["bitrate"] // 1000) # kbps

        # Easy access tags / ID3
        if hasattr(audio, "tags") and audio.tags:
            tags = audio.tags

            # Extract basic tags
            def get_tag_value(keys):
                for key in keys:
                    if key in tags:
                        val = tags[key]
                        if isinstance(val, (list, tuple)) and len(val) > 0:
                            return str(val[0]).strip()
                        return str(val).strip()
                return None

            title = get_tag_value(["TIT2", "title", "\xa9nam", "TITLE"])
            artist = get_tag_value(["TPE1", "artist", "\xa9ART", "ARTIST", "TPE2", "albumartist"])
            album = get_tag_value(["TALB", "album", "\xa9alb", "ALBUM"])
            genre = get_tag_value(["TCON", "genre", "\xa9gen", "GENRE"])
            year_val = get_tag_value(["TDRC", "date", "\xa9day", "DATE", "TYER"])

            if title:
                metadata["title"] = title
            if artist:
                metadata["artist"] = artist
            if album:
                metadata["album"] = album
            if genre:
                metadata["genre"] = genre
            if year_val:
                try:
                    # Take first 4 digits
                    digits = ''.join(c for c in str(year_val) if c.isdigit())
                    if len(digits) >= 4:
                        metadata["year"] = int(digits[:4])
                except Exception:
                    pass

            # Extract artwork
            artwork_data = None
            artwork_ext = ".jpg"

            # 1. MP3 / ID3 APIC frames
            if isinstance(audio, MP3) or hasattr(tags, "getall"):
                for tag_name in ["APIC:", "APIC:Cover", "APIC"]:
                    if tag_name in tags:
                        frame = tags[tag_name]
                        artwork_data = frame.data
                        if "png" in getattr(frame, "mime", "").lower():
                            artwork_ext = ".png"
                        break
                if not artwork_data and hasattr(tags, "values"):
                    for val in tags.values():
                        if isinstance(val, APIC):
                            artwork_data = val.data
                            if "png" in getattr(val, "mime", "").lower():
                                artwork_ext = ".png"
                            break

            # 2. FLAC pictures
            elif isinstance(audio, FLAC) and audio.pictures:
                pic = audio.pictures[0]
                artwork_data = pic.data
                if "png" in pic.mime.lower():
                    artwork_ext = ".png"

            # 3. MP4 / M4A covr
            elif isinstance(audio, MP4) and "covr" in audio.tags:
                covers = audio.tags["covr"]
                if covers:
                    artwork_data = bytes(covers[0])
                    if covers[0].imageformat == MP4Cover.FORMAT_PNG:
                        artwork_ext = ".png"

            # Save extracted artwork
            if artwork_data:
                art_id = f"art_{uuid.uuid4().hex[:12]}{artwork_ext}"
                art_dest = settings.artwork_path / art_id
                with open(art_dest, "wb") as f:
                    f.write(artwork_data)
                metadata["artwork_filename"] = art_id

    except Exception as e:
        # Fall back to file stem
        pass

    return metadata
