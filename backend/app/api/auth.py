import hmac
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..config import settings
from ..security import (COOKIE_MAX_AGE, COOKIE_NAME, auth_enabled, clear_login_failures, client_ip,
                        is_authenticated, login_retry_after, record_login_failure, session_token)

router = APIRouter(tags=["Auth"])


class LoginRequest(BaseModel):
    password: str = ""


@router.get("/auth/status")
def auth_status(request: Request):
    return {"auth_required": auth_enabled(), "authenticated": is_authenticated(request)}


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response):
    if not auth_enabled():
        return {"ok": True}

    ip = client_ip(request)
    wait = login_retry_after(ip)
    if wait:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            status_code=429,
            detail=f"Too many wrong passwords. Try again in about {minutes} minute(s).",
            headers={"Retry-After": str(wait)},
        )

    if not hmac.compare_digest(payload.password.encode(), settings.ACCESS_PASSWORD.encode()):
        record_login_failure(ip)
        time.sleep(0.5)  # slows down guessing even further
        raise HTTPException(status_code=401, detail="Wrong password")

    clear_login_failures(ip)
    response.set_cookie(
        COOKIE_NAME, session_token(),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/",
        secure=request.url.scheme == "https",  # behind HTTPS the cookie is never sent over plain HTTP
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}
