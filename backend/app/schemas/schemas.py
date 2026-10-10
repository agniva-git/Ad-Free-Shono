from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict

# --- Artist Schemas ---
class ArtistBase(BaseModel):
    name: str

class ArtistResponse(ArtistBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    artwork_path: Optional[str] = None
    created_at: datetime
    song_count: Optional[int] = 0

# --- Album Schemas ---
class AlbumBase(BaseModel):
    title: str
    year: Optional[int] = None

class AlbumResponse(AlbumBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    artist_id: Optional[str] = None
    artist_name: Optional[str] = None
    artwork_path: Optional[str] = None
    created_at: datetime
    song_count: Optional[int] = 0

# --- Song Schemas ---
class SongBase(BaseModel):
    title: str
    genre: Optional[str] = None

class SongUpdate(BaseModel):
    title: Optional[str] = None
    artist_name: Optional[str] = None
    album_title: Optional[str] = None
    genre: Optional[str] = None

class SongResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    artist_id: Optional[str] = None
    artist_name: Optional[str] = "Unknown Artist"
    album_id: Optional[str] = None
    album_title: Optional[str] = "Unknown Album"
    artwork_url: Optional[str] = None
    duration_seconds: float
    genre: Optional[str] = None
    file_size: int
    bitrate: Optional[int] = None
    created_at: datetime
    is_favorite: bool = False
    can_edit: bool = False

# --- Playlist Schemas ---
class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None

class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class PlaylistSongItem(BaseModel):
    position: int
    song: SongResponse

class PlaylistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    song_count: int = 0
    songs: List[SongResponse] = []

class PlaylistAddSong(BaseModel):
    song_id: str

# --- Stats Schema ---
class LibraryStats(BaseModel):
    total_songs: int
    total_artists: int
    total_albums: int
    total_playlists: int
    total_duration_seconds: float


# --- User Schemas ---
class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    role: str

class UserAdminView(UserPublic):
    is_active: bool
    created_at: datetime
    upload_count: int = 0

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "member"

class UserAdminUpdate(BaseModel):
    password: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None

class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""

class PasswordChange(BaseModel):
    current_password: str
    new_password: str
