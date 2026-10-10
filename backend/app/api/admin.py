from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Song, User
from ..schemas import UserAdminUpdate, UserAdminView, UserCreate
from ..services.accounts import active_admin_count, create_user, set_password

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


def _view(db: Session, user: User) -> UserAdminView:
    uploads = db.query(func.count(Song.id)).filter(Song.uploaded_by == user.id).scalar() or 0
    return UserAdminView(id=user.id, username=user.username, role=user.role, is_active=user.is_active,
                         created_at=user.created_at, upload_count=uploads)


@router.get("/users", response_model=List[UserAdminView])
def list_users(db: Session = Depends(get_db)):
    return [_view(db, u) for u in db.query(User).order_by(User.created_at.asc()).all()]


@router.post("/users", response_model=UserAdminView, status_code=201)
def add_user(payload: UserCreate, db: Session = Depends(get_db)):
    try:
        user = create_user(db, payload.username, payload.password, payload.role)
    except ValueError as err:
        raise HTTPException(status_code=409 if "taken" in str(err) else 400, detail=str(err))
    return _view(db, user)


@router.patch("/users/{user_id}", response_model=UserAdminView)
def update_user(user_id: str, payload: UserAdminUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    losing_admin = (payload.is_active is False and user.role == "admin") or \
                   (payload.role == "member" and user.role == "admin")
    if user.id == admin.id and (payload.is_active is False or payload.role == "member"):
        raise HTTPException(status_code=400, detail="You cannot disable or demote your own account.")
    if losing_admin and active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="There must always be at least one active admin.")
    if payload.role is not None and payload.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'.")

    if payload.password is not None:
        try:
            set_password(db, user, payload.password)  # also signs that account out everywhere
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err))
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role is not None:
        user.role = payload.role
    db.commit()
    db.refresh(user)
    return _view(db, user)
