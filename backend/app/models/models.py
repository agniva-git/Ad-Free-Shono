import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, String, Integer, Float, DateTime, ForeignKey, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from ..database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(32), nullable=False, unique=True, index=True)  # always stored lowercase
    password_hash = Column(String(255), nullable=False)
    role = Column(String(10), nullable=False, default="member")  # "admin" | "member"
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utc_now)

class Artist(Base):
    __tablename__ = "artists"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, unique=True, index=True)
    artwork_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    albums = relationship("Album", back_populates="artist", cascade="all, delete-orphan")
    songs = relationship("Song", back_populates="artist")

class Album(Base):
    __tablename__ = "albums"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False, index=True)
    artist_id = Column(String(36), ForeignKey("artists.id", ondelete="SET NULL"), nullable=True)
    artwork_path = Column(String(500), nullable=True)
    year = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    artist = relationship("Artist", back_populates="albums")
    songs = relationship("Song", back_populates="album")

class Song(Base):
    __tablename__ = "songs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False, index=True)
    artist_id = Column(String(36), ForeignKey("artists.id", ondelete="SET NULL"), nullable=True)
    album_id = Column(String(36), ForeignKey("albums.id", ondelete="SET NULL"), nullable=True)
    audio_path = Column(String(500), nullable=False) # Relative to storage directory or filename
    original_filename = Column(String(255), nullable=True)
    duration_seconds = Column(Float, default=0.0)
    genre = Column(String(100), nullable=True)
    file_size = Column(Integer, default=0)
    bitrate = Column(Integer, nullable=True)
    uploaded_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    file_hash = Column(String(64), nullable=True)  # sha256 of uploads, used to refuse duplicates
    created_at = Column(DateTime, default=utc_now)

    artist = relationship("Artist", back_populates="songs")
    album = relationship("Album", back_populates="songs")
    playlist_entries = relationship("PlaylistSong", back_populates="song", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="song", cascade="all, delete-orphan")
    history = relationship("PlayHistory", back_populates="song", cascade="all, delete-orphan", passive_deletes=True)

class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)  # owner; playlists are private
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    songs = relationship("PlaylistSong", back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistSong.position")

class PlaylistSong(Base):
    __tablename__ = "playlist_songs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    playlist_id = Column(String(36), ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False)
    song_id = Column(String(36), ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, default=0)

    playlist = relationship("Playlist", back_populates="songs")
    song = relationship("Song", back_populates="playlist_entries")

    __table_args__ = (
        UniqueConstraint("playlist_id", "song_id", name="uq_playlist_song"),
    )

class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    song_id = Column(String(36), ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utc_now)

    song = relationship("Song", back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "song_id", name="uq_favorite_user_song"),
    )

class PlayHistory(Base):
    __tablename__ = "play_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    song_id = Column(String(36), ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    played_at = Column(DateTime, default=utc_now)

    song = relationship("Song", back_populates="history")
