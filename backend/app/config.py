from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # .env is read from the project root, not from whatever folder you launched from
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    PROJECT_NAME: str = "AdFreeShono"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    DATA_DIR: str = "./data"
    DATABASE_URL: str = "sqlite:///./data/music.db"

    MUSIC_DIR: str = "./data/media/audio"
    ARTWORK_DIR: str = "./data/media/artwork"

    # The first admin account is created from these on first start (if no admin exists yet).
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""
    SECRET_KEY: str = "change-this-to-a-long-random-string"

    MAX_UPLOAD_MB: int = 500        # largest single file
    MEMBER_QUOTA_MB: int = 5000     # total uploads allowed per friend account (admins are unlimited)

    def _resolve(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else (BASE_DIR / p).resolve()

    @property
    def music_path(self) -> Path:
        return self._resolve(self.MUSIC_DIR)

    @property
    def artwork_path(self) -> Path:
        return self._resolve(self.ARTWORK_DIR)

    @property
    def data_path(self) -> Path:
        return self._resolve(self.DATA_DIR)

    @property
    def database_url(self) -> str:
        """DATABASE_URL with a relative sqlite path anchored to the project root."""
        url = make_url(self.DATABASE_URL)
        if url.drivername.startswith("sqlite") and url.database not in (None, "", ":memory:"):
            db_path = self._resolve(url.database)
            return f"sqlite:///{db_path.as_posix()}"
        return self.DATABASE_URL

    @property
    def db_file(self) -> Path | None:
        url = make_url(self.database_url)
        if url.drivername.startswith("sqlite") and url.database not in (None, "", ":memory:"):
            return Path(url.database)
        return None

    def ensure_directories(self):
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.music_path.mkdir(parents=True, exist_ok=True)
        self.artwork_path.mkdir(parents=True, exist_ok=True)
        if self.db_file:
            self.db_file.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
