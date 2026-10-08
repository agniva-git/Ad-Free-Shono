from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..security import get_current_user
from ..services.scanner import is_safe_directory, scan_directory

router = APIRouter(prefix="/scan", tags=["Scan"])


class ScanRequest(BaseModel):
    directory_path: Optional[str] = None
    copy_to_storage: bool = False


@router.post("")
def trigger_scan(payload: ScanRequest, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    target = Path(payload.directory_path).expanduser() if payload.directory_path else settings.music_path

    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder does not exist: {target}")
    if not is_safe_directory(target):
        raise HTTPException(status_code=403, detail="Scanning this system folder is restricted.")

    return scan_directory(target, db, copy_to_storage=payload.copy_to_storage)
