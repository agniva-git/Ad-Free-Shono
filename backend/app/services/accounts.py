import re
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Favorite, PlayHistory, Playlist, User
from ..security import hash_password, password_problems

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")


def normalize_username(raw: str) -> str:
    return (raw or "").strip().lower()


def create_user(db: Session, username: str, password: str, role: str = "member") -> User:
    """Validates and creates an account. Raises ValueError with a readable message."""
    name = normalize_username(username)
    if not USERNAME_RE.match(name):
        raise ValueError("Username must be 3-32 characters: letters, numbers, dot, dash or underscore.")
    if role not in ("admin", "member"):
        raise ValueError("Role must be 'admin' or 'member'.")
    problems = password_problems(password, name)
    if problems:
        raise ValueError(" ".join(problems))
    if db.query(User).filter(User.username == name).first():
        raise ValueError("That username is already taken.")
    user = User(username=name, password_hash=hash_password(password), role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: User, new_password: str) -> None:
    problems = password_problems(new_password, user.username)
    if problems:
        raise ValueError(" ".join(problems))
    user.password_hash = hash_password(new_password)  # this also logs the account out everywhere
    db.commit()


def active_admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()


def bootstrap_admin(db: Session) -> Optional[User]:
    """On first start (no admin yet) create the admin from ADMIN_USERNAME / ADMIN_PASSWORD."""
    if db.query(User).filter(User.role == "admin").first():
        return None
    name = normalize_username(settings.ADMIN_USERNAME)
    problems = password_problems(settings.ADMIN_PASSWORD, name)
    if not USERNAME_RE.match(name):
        problems.append("ADMIN_USERNAME must be 3-32 characters: letters, numbers, dot, dash or underscore.")
    if problems:
        raise RuntimeError(
            "Refusing to start: there is no admin account yet and ADMIN_PASSWORD / ADMIN_USERNAME in .env "
            "are not usable:\n  - " + "\n  - ".join(problems))
    return create_user(db, name, settings.ADMIN_PASSWORD, role="admin")


def assign_legacy_rows(db: Session) -> None:
    """Rows created before accounts existed (likes, history, playlists) go to the first admin."""
    admin = db.query(User).filter(User.role == "admin").order_by(User.created_at).first()
    if not admin:
        return
    for model in (Playlist, Favorite, PlayHistory):
        db.query(model).filter(model.user_id.is_(None)).update({model.user_id: admin.id}, synchronize_session=False)
    db.commit()
