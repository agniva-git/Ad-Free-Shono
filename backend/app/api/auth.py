import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import (
    COOKIE_MAX_AGE, COOKIE_NAME,
    clear_login_failures, client_ip,
    get_user_id_from_cookie,
    hash_password, login_retry_after,
    record_login_failure, session_token,
    verify_password, get_current_user,
)

router = APIRouter(tags=["Auth"])


# ---------- schemas ----------

class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


class RegisterRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Username must be at least 2 characters")
        if len(v) > 50:
            raise ValueError("Username must be at most 50 characters")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# ---------- endpoints ----------

@router.get("/auth/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    user_id = get_user_id_from_cookie(request)
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return {
                "authenticated": True,
                "user_id": user.id,
                "username": user.username,
                "is_admin": user.is_admin,
            }
    return {"authenticated": False}


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response,
          db: Session = Depends(get_db)):
    ip = client_ip(request)
    wait = login_retry_after(ip)
    if wait:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed logins. Try again in about {minutes} minute(s).",
            headers={"Retry-After": str(wait)},
        )

    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        record_login_failure(ip)
        time.sleep(0.5)
        raise HTTPException(status_code=401, detail="Wrong username or password")

    clear_login_failures(ip)
    response.set_cookie(
        COOKIE_NAME, session_token(user.id),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/",
        secure=request.url.scheme == "https",
    )
    return {"ok": True, "user_id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/auth/register", status_code=201)
def register(payload: RegisterRequest, request: Request,
             db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    """Create a new user account. Only admins may do this (no open signup)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can create accounts")

    username = payload.username
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail=f"Username '{username}' is already taken")

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.get("/auth/users")
def list_users(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    """List all users. Admin only."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    users = db.query(User).order_by(User.created_at).all()
    return [{"id": u.id, "username": u.username, "is_admin": u.is_admin, "created_at": u.created_at} for u in users]


@router.delete("/auth/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    """Delete a user account. Admin only. Cannot delete yourself."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": f"User '{user.username}' deleted"}
