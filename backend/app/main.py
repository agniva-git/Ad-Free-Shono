from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi import Depends

from .api import admin, albums, artists, artwork, auth, playlists, scan, search, songs, stats, upload
from .config import settings
from .database import Base, SessionLocal, engine
from .deps import get_current_user
from .security import add_security_headers, check_security_config, guard_api
from .services.accounts import assign_legacy_rows, bootstrap_admin
from .services.migrate import migrate_schema
from .services.library import prune_empty, sweep_unused_artwork

check_security_config()  # stops the server if the secret key is missing or a placeholder
settings.ensure_directories()
migrate_schema(engine)  # upgrades a database made before accounts existed
Base.metadata.create_all(bind=engine)


def startup_cleanup():
    """Creates the first admin, adopts old rows, and clears leftovers (empty artists/albums, orphan rows, duplicate covers)."""
    db = SessionLocal()
    try:
        bootstrap_admin(db)
        assign_legacy_rows(db)
        prune_empty(db)
        sweep_unused_artwork(db)
    finally:
        db.close()


startup_cleanup()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Zero-Cost Personal Music Cloud and Streaming Server",
    version="1.2.0",
    # The auto-generated API docs are only available while DEBUG is on
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# The frontend is served by this same app, so no CORS is needed. Without CORS, other
# websites cannot read the API from a browser. The guard also blocks cross-origin
# writes; every other route requires a signed-in account (see deps.py).
app.middleware("http")(guard_api)
app.middleware("http")(add_security_headers)  # added last, so it wraps every response

# Everything except login/health needs a signed-in account
app.include_router(auth.router, prefix="/api")
for module in (artwork, songs, artists, albums, playlists, upload, search, stats, scan):
    app.include_router(module.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(admin.router, prefix="/api")  # admin-only (checked inside the router)


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
