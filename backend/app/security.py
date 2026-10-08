import hashlib
import hmac
import threading
import time
from urllib.parse import urlparse

import bcrypt as _bcrypt
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db

COOKIE_NAME = "adfree_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
PUBLIC_API_PATHS = {"/api/health", "/api/login", "/api/logout", "/api/auth/status"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
PLACEHOLDER_WORDS = ("change-me", "change-this", "replace-with", "any-long", "pick-a-password",
                     "your own password", "generated value", "example")
COMMON_PASSWORDS = {"password", "password1", "12345678", "123456789", "qwertyuiop", "adminadmin",
                    "letmein123", "hunter2", "adfreeshono", "iloveyou"}

CSP = ("default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


# ---------- startup safety check ----------

def check_security_config() -> None:
    """Refuse to start with a configuration that would leave the library open or guessable."""
    problems = []
    key = settings.SECRET_KEY

    if len(key) < 32 or any(w in key.lower() for w in PLACEHOLDER_WORDS):
        problems.append("SECRET_KEY is missing, too short (under 32 characters) or still a placeholder. "
                        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")

    if problems:
        raise RuntimeError("Refusing to start because of unsafe settings in .env:\n  - " + "\n  - ".join(problems))


# ---------- password hashing (bcrypt 4+) ----------

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ---------- login attempt limiting ----------

LOGIN_FAIL_LIMIT = 5
LOGIN_WINDOW_SECONDS = 15 * 60
_failures: dict = {}
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def login_retry_after(ip: str) -> int:
    """Seconds until this address may try again (0 means it may try now)."""
    now = time.time()
    with _lock:
        recent = [t for t in _failures.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
        _failures[ip] = recent
        if len(recent) >= LOGIN_FAIL_LIMIT:
            return int(LOGIN_WINDOW_SECONDS - (now - recent[0])) + 1
        return 0


def record_login_failure(ip: str) -> None:
    with _lock:
        if len(_failures) > 5000:
            _failures.clear()
        _failures.setdefault(ip, []).append(time.time())


def clear_login_failures(ip: str) -> None:
    with _lock:
        _failures.pop(ip, None)


def reset_login_limiter() -> None:
    with _lock:
        _failures.clear()


# ---------- session tokens (encode user_id) ----------

def session_token(user_id: str) -> str:
    """Produce a tamper-evident cookie value for a specific user."""
    msg = f"session:{user_id}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest() + ":" + user_id


def _parse_token(token: str) -> str | None:
    """Return user_id if the token is valid, else None."""
    if ":" not in token:
        return None
    sig, _, user_id = token.partition(":")
    expected_sig = hmac.new(settings.SECRET_KEY.encode(), f"session:{user_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    return user_id


def get_user_id_from_cookie(request: Request) -> str | None:
    """Extract and verify the user_id from the session cookie."""
    token = request.cookies.get(COOKIE_NAME, "")
    return _parse_token(token) if token else None


# ---------- FastAPI dependency for current user ----------

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """FastAPI dependency — returns the logged-in User ORM object.
    Raises 401 if not authenticated.
    """
    from .models import User
    user_id = get_user_id_from_cookie(request)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Login required")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------- request guards (middleware) ----------

def is_authenticated(request: Request) -> bool:
    return get_user_id_from_cookie(request) is not None


def is_same_origin(request: Request) -> bool:
    """Browsers attach Origin to cross-site writes; reject unless it is this server."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    return urlparse(origin).netloc == request.headers.get("host", "")


async def guard_api(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        if request.method not in SAFE_METHODS and not is_same_origin(request):
            return JSONResponse(status_code=403, content={"detail": "Cross-origin request blocked"})
        if path not in PUBLIC_API_PATHS and not is_authenticated(request):
            return JSONResponse(status_code=401, content={"detail": "Login required"})
    return await call_next(request)


async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "same-origin"
    h["Content-Security-Policy"] = CSP
    if request.url.scheme == "https":
        h["Strict-Transport-Security"] = "max-age=31536000"
    return response
