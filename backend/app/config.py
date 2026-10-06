import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Personal Music Cloud"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./data/music.db"

    # Audio & Artwork Storage paths
    MUSIC_DIR: str = "./data/media/audio"
    ARTWORK_DIR: str = "./data/media/artwork"

    ALLOWED_ORIGINS: str = "*"
    SECRET_KEY: str = "personal-music-cloud-secret-key-change-in-prod"

    @property
    def music_path(self) -> Path:
        p = Path(self.MUSIC_DIR)
        return p if p.is_absolute() else (BASE_DIR / p).resolve()

    @property
    def artwork_path(self) -> Path:
        p = Path(self.ARTWORK_DIR)
        return p if p.is_absolute() else (BASE_DIR / p).resolve()

    @property
    def data_path(self) -> Path:
        return (BASE_DIR / "data").resolve()

    def ensure_directories(self):
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.music_path.mkdir(parents=True, exist_ok=True)
        self.artwork_path.mkdir(parents=True, exist_ok=True)

settings = Settings()
