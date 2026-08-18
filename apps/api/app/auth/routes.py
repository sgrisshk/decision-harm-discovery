from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.schemas import LoginRequest, UserRead
from app.auth import service
from app.auth.dependencies import SESSION_COOKIE_NAME, get_current_user
from app.core.config import get_settings
from app.db.models import UserModel
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_is_secure() -> bool:
    # Can't require Secure over local http://localhost; real deployments run staging/production
    # over HTTPS (`docs/operations/deployment.md`).
    return get_settings().app_env in {"staging", "production"}


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
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_model.token,
        max_age=int(service.SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=_cookie_is_secure(),
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, session: Session = Depends(get_db)) -> None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        service.delete_session(session, token)
        session.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserRead)
def me(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    return current_user
