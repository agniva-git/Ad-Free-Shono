import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from .config import settings
from .database import engine, Base
from .api import songs, artists, albums, playlists, upload, search, stats, scan

# Ensure required directories exist
settings.ensure_directories()

# Initialize tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Zero-Cost Personal Music Cloud and Streaming Server",
    version="1.0.0"
)

# CORS configuration (allows phone / other devices on home network)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount artwork directory
app.mount("/api/artwork", StaticFiles(directory=str(settings.artwork_path)), name="artwork")

# Include API Routers
app.include_router(songs.router, prefix="/api")
app.include_router(artists.router, prefix="/api")
app.include_router(albums.router, prefix="/api")
app.include_router(playlists.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(scan.router, prefix="/api")

# Health check
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "mode": "zero-cost-local-first",
        "storage_path": str(settings.music_path)
    }

# Frontend static serving
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # If API route not found, let it 404
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "API route not found"})

        file_candidate = FRONTEND_DIR / full_path
        if full_path and file_candidate.exists() and file_candidate.is_file():
            return FileResponse(str(file_candidate))

        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))

        return JSONResponse(status_code=404, content={"detail": "Frontend index.html not found"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
