import hashlib
import hmac
import os
import threading
import time
from typing import Optional
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import settings

COOKIE_NAME = "adfree_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

MIN_PASSWORD_LENGTH = 10
PLACEHOLDER_WORDS = ("change-me", "change-this", "replace-with", "any-long", "pick-a-password",
                     "your own password", "generated value", "example")
COMMON_PASSWORDS = {"password", "password1", "12345678", "123456789", "1234567890", "qwertyuiop",
                    "adminadmin", "letmein123", "hunter2", "adfreeshono", "iloveyou"}

CSP = ("default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


# ---------- startup safety check ----------

def secret_key_problem() -> Optional[str]:
    key = settings.SECRET_KEY
    if len(key) < 32 or any(w in key.lower() for w in PLACEHOLDER_WORDS):
        return ("SECRET_KEY is missing, too short (under 32 characters) or still a placeholder. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    return None


def check_security_config() -> None:
    """Refuse to start when the key that signs login cookies is weak or a placeholder."""
    problem = secret_key_problem()
    if problem:
        raise RuntimeError("Refusing to start because of unsafe settings in .env:\n  - " + problem)


# ---------- passwords ----------

def password_problems(password: str, username: str = "") -> list:
    problems = []
    low = password.lower()
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if low in COMMON_PASSWORDS or any(w in low for w in PLACEHOLDER_WORDS):
        problems.append("That password is a placeholder or a very common one. Choose another.")
    if username and low == username.lower():
        problems.append("Password must not be the same as the username.")
    return problems


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${2 ** 14}$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, n, r, p, salt_hex, digest_hex = stored.split("$")
        expected = bytes.fromhex(digest_hex)
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


# Verified when a username does not exist, so a wrong username takes as long as a wrong password
DUMMY_HASH = hash_password("not-a-real-account-password")


# ---------- sessions (signed cookie: "<user id>.<signature>") ----------
# The signature covers the user's current password hash, so changing or resetting a
# password immediately logs that account out everywhere.

def _signature(user_id: str, password_hash: str) -> str:
    msg = f"{user_id}:{password_hash}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def make_session_cookie(user) -> str:
    return f"{user.id}.{_signature(user.id, user.password_hash)}"


def user_from_request(request: Request, db: Session):
    from .models import User  # imported here to avoid a circular import at startup
    cookie = request.cookies.get(COOKIE_NAME, "")
    user_id, _, supplied = cookie.partition(".")
    if not user_id or not supplied:
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return None
    if not hmac.compare_digest(supplied, _signature(user.id, user.password_hash)):
        return None
    return user


# ---------- login attempt limiting ----------

LOGIN_FAIL_LIMIT = 5
LOGIN_WINDOW_SECONDS = 15 * 60
_failures: dict = {}
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    # Behind the reverse proxy, uvicorn already replaces this with the real visitor address
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
        if len(_failures) > 5000:  # keep memory bounded
            _failures.clear()
        _failures.setdefault(ip, []).append(time.time())


def clear_login_failures(ip: str) -> None:
    with _lock:
        _failures.pop(ip, None)


def reset_login_limiter() -> None:
    with _lock:
        _failures.clear()


# ---------- request guards ----------

def is_same_origin(request: Request) -> bool:
    """Browsers attach Origin to cross-site writes; reject it unless it is this server."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    return urlparse(origin).netloc == request.headers.get("host", "")


async def guard_api(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method not in SAFE_METHODS and not is_same_origin(request):
        return JSONResponse(status_code=403, content={"detail": "Cross-origin request blocked"})
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
