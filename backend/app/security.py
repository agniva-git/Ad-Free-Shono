import hashlib
import hmac
import threading
import time
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import settings

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
    pw, key = settings.ACCESS_PASSWORD, settings.SECRET_KEY

    if not pw:
        if settings.HOST not in LOOPBACK_HOSTS:
            problems.append(
                f"ACCESS_PASSWORD is empty but HOST={settings.HOST} lets other devices connect. "
                "Set ACCESS_PASSWORD, or set HOST=127.0.0.1.")
    else:
        low = pw.lower()
        if len(pw) < 10:
            problems.append("ACCESS_PASSWORD is shorter than 10 characters.")
        if low in COMMON_PASSWORDS or any(w in low for w in PLACEHOLDER_WORDS):
            problems.append("ACCESS_PASSWORD is a placeholder or a common password. Choose your own.")
        if len(key) < 32 or any(w in key.lower() for w in PLACEHOLDER_WORDS):
            problems.append("SECRET_KEY is missing, too short (under 32 characters) or still a placeholder. "
                            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")

    if problems:
        raise RuntimeError("Refusing to start because of unsafe settings in .env:\n  - " + "\n  - ".join(problems))


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


# ---------- session + request guards ----------

def auth_enabled() -> bool:
    return bool(settings.ACCESS_PASSWORD)


def session_token() -> str:
    msg = ("session:" + settings.ACCESS_PASSWORD).encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def is_authenticated(request: Request) -> bool:
    if not auth_enabled():
        return True
    supplied = request.cookies.get(COOKIE_NAME, "")
    return hmac.compare_digest(supplied, session_token())


def is_same_origin(request: Request) -> bool:
    """Browsers attach Origin to cross-site writes; reject it unless it is this server."""
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
