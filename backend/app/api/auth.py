import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import LoginRequest, PasswordChange, UserPublic
from ..security import (COOKIE_MAX_AGE, COOKIE_NAME, DUMMY_HASH, clear_login_failures, client_ip,
                        login_retry_after, make_session_cookie, record_login_failure,
                        user_from_request, verify_password)
from ..services.accounts import normalize_username, set_password

router = APIRouter(tags=["Auth"])


def _set_session_cookie(response: Response, request: Request, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME, make_session_cookie(user),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/",
        secure=request.url.scheme == "https",  # behind HTTPS the cookie is never sent over plain HTTP
    )


@router.get("/auth/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    user = user_from_request(request, db)
    return {"authenticated": bool(user), "user": UserPublic.model_validate(user) if user else None}


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    wait = login_retry_after(ip)
    if wait:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            status_code=429,
            detail=f"Too many wrong attempts. Try again in about {minutes} minute(s).",
            headers={"Retry-After": str(wait)},
        )

    user = db.query(User).filter(User.username == normalize_username(payload.username)).first()
    # always do one password check, so a wrong username takes as long as a wrong password
    password_ok = verify_password(payload.password, user.password_hash if user else DUMMY_HASH)
    if not (user and user.is_active and password_ok):
        record_login_failure(ip)
        time.sleep(0.5)  # slows down guessing even further
        raise HTTPException(status_code=401, detail="Wrong username or password")

    clear_login_failures(ip)
    _set_session_cookie(response, request, user)
    return {"ok": True, "user": UserPublic.model_validate(user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/me/password")
def change_own_password(payload: PasswordChange, request: Request, response: Response,
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="Current password is wrong")
    try:
        set_password(db, user, payload.new_password)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    # changing the password signs out every other device; keep this one signed in
    _set_session_cookie(response, request, user)
    return {"ok": True}
