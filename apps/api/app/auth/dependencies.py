from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import service
from app.db.models import UserModel
from app.db.session import get_db

SESSION_COOKIE_NAME = "sf_session"


def get_current_user(request: Request, session: Session = Depends(get_db)) -> UserModel:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = service.get_user_for_token(session, token) if token else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
