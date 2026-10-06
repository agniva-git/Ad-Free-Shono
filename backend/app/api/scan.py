from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.scanner import scan_directory
from ..config import settings

router = APIRouter(prefix="/scan", tags=["Scan"])

class ScanRequest(BaseModel):
    directory_path: Optional[str] = None
    copy_to_storage: bool = False

@router.post("")
def trigger_scan(payload: ScanRequest, db: Session = Depends(get_db)):
    if payload.directory_path:
        target_path = Path(payload.directory_path)
    else:
        target_path = settings.music_path

    if not target_path.exists():
        raise HTTPException(status_code=400, detail=f"Target directory does not exist: {str(target_path)}")

    results = scan_directory(target_path, db, copy_to_storage=payload.copy_to_storage)
    return results
