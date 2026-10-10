import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import settings

router = APIRouter(tags=["Artwork"])

SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


@router.get("/artwork/{name}")
def get_artwork(name: str):
    """Cover images. Served through the API (not a public static folder) so a login is required."""
    base = settings.artwork_path.resolve()
    path = (base / name).resolve() if SAFE_NAME.match(name) else None
    if not path or not path.is_file() or not path.is_relative_to(base):
        raise HTTPException(status_code=404, detail="Artwork not found")
    # file names are named after their content, so they can be cached by the browser
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})
