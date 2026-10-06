from typing import Optional
from ..models import Song
from ..schemas import SongResponse

def format_song_response(song: Song) -> SongResponse:
    artwork_url = None
    if song.album and song.album.artwork_path:
        artwork_url = f"/api/artwork/{song.album.artwork_path}"
    elif song.artist and song.artist.artwork_path:
        artwork_url = f"/api/artwork/{song.artist.artwork_path}"

    return SongResponse(
        id=song.id,
        title=song.title,
        artist_id=song.artist_id,
        artist_name=song.artist.name if song.artist else "Unknown Artist",
        album_id=song.album_id,
        album_title=song.album.title if song.album else "Unknown Album",
        artwork_url=artwork_url,
        duration_seconds=song.duration_seconds,
        genre=song.genre,
        file_size=song.file_size,
        bitrate=song.bitrate,
        created_at=song.created_at,
        is_favorite=bool(song.favorite_entry)
    )
