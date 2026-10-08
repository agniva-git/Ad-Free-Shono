from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import albums, artists, auth, playlists, scan, search, songs, stats, upload
from .config import settings
from .database import Base, SessionLocal, engine
from .security import add_security_headers, check_security_config, guard_api, hash_password
from .services.library import prune_empty, sweep_unused_artwork

check_security_config()  # stops the server if the secret key is missing or a placeholder
settings.ensure_directories()
Base.metadata.create_all(bind=engine)


def bootstrap_admin():
    """If no users exist yet, create the initial admin account from ADMIN_USERNAME / ADMIN_PASSWORD.
    This only runs once — after that, admins manage accounts through the API.
    """
    from .models import User
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            uname = settings.ADMIN_USERNAME
            pw = settings.ADMIN_PASSWORD
            if uname and pw:
                admin = User(
                    username=uname,
                    password_hash=hash_password(pw),
                    is_admin=True,
                )
                db.add(admin)
                db.commit()
                print(f"[AdFreeShono] Created initial admin account: {uname!r}")
            else:
                print("[AdFreeShono] WARNING: No users exist and ADMIN_USERNAME/ADMIN_PASSWORD are not set. "
                      "Set them in .env and restart to create the first admin account.")
    finally:
        db.close()


def startup_cleanup():
    """Clears leftovers from older versions (empty artists/albums, orphan rows, duplicate covers)."""
    db = SessionLocal()
    try:
        prune_empty(db)
        sweep_unused_artwork(db)
    finally:
        db.close()


bootstrap_admin()
startup_cleanup()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Zero-Cost Personal Music Cloud and Streaming Server",
    version="2.0.0",
    # The auto-generated API docs are only available while DEBUG is on
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# The frontend is served by this same app, so no CORS is needed. Without CORS, other
# websites cannot read the API from a browser. The guard also blocks cross-origin
# writes and enforces the login cookie.
app.middleware("http")(guard_api)
app.middleware("http")(add_security_headers)  # added last, so it wraps every response

app.mount("/api/artwork", StaticFiles(directory=str(settings.artwork_path)), name="artwork")

for module in (auth, songs, artists, albums, playlists, upload, search, stats, scan):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": settings.PROJECT_NAME}


FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

if FRONTEND_DIR.exists():
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "API route not found"})

        candidate = (FRONTEND_DIR / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIR.resolve()):
            return FileResponse(str(candidate))

        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse(status_code=404, content={"detail": "Frontend index.html not found"})
