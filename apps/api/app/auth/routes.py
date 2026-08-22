from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.schemas import LoginRequest, UserRead
from app.auth import service
from app.auth.dependencies import SESSION_COOKIE_NAME, get_current_user
from app.core.config import get_settings
from app.db.models import UserModel
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_security() -> tuple[bool, Literal["lax", "none"]]:
    """Session cookie `Secure`/`SameSite` attributes.

    Outside development/test, the frontend and API are not guaranteed to share a
    registrable domain (e.g. a GitHub Pages frontend and Render's `*.onrender.com`
    backend, unless the custom-domain setup in `docs/operations/deployment.md` is in
    place) — that makes every request cross-site from the cookie's point of view.
    `SameSite=Lax` is dropped by the browser on cross-site requests, so login would
    "succeed" (200, Set-Cookie sent) while the browser silently never stores or
    resends the cookie. `SameSite=None` fixes that, but browsers require `Secure=true`
    whenever `SameSite=None` is set, so the two must always travel together.

    In development (and CI's `test` env) we run over plain `http://localhost`, where a
    `Secure=true` cookie isn't stored at all — `SameSite=None` there would silently
    break the cookie instead of fixing it. Both of those envs' real topology today is
    same-origin (docker-compose serves frontend+backend from one host in dev; the test
    client is same-process), so plain `SameSite=Lax` without `Secure` is the correct,
    working choice there. This is a known, narrow limitation: if development ever needs
    a genuinely cross-site setup, this branch must move to a real HTTPS dev proxy rather
    than silently attempting `None` without `Secure`.
    """
    if get_settings().app_env in {"staging", "production"}:
        return True, "none"
    return False, "lax"


@router.post("/login", response_model=UserRead)
def login(
    payload: LoginRequest, response: Response, session: Session = Depends(get_db)
) -> UserModel:
    user = service.authenticate(session, payload.email, payload.password)
    if user is None:
        # Deliberately generic: never confirms whether the email itself has an account.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    session_model = service.create_session(session, user.id)
    session.commit()
    secure, samesite = _cookie_security()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_model.token,
        max_age=int(service.SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite=samesite,
        secure=secure,
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, session: Session = Depends(get_db)) -> None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        service.delete_session(session, token)
        session.commit()
    secure, samesite = _cookie_security()
    # Attributes must match how the cookie was set: some browsers refuse to let a
    # non-Secure Set-Cookie overwrite/clear a Secure one (RFC 6265bis "Leave Secure
    # Cookies Alone"), which would make logout silently fail to clear the cookie.
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=secure, samesite=samesite)


@router.get("/me", response_model=UserRead)
def me(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    return current_user
