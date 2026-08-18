from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import generate_session_token, verify_password
from app.db.models import SessionModel, UserModel

SESSION_LIFETIME = timedelta(days=7)


def authenticate(session: Session, email: str, password: str) -> UserModel | None:
    """Returns `None` on any failure (unknown email or wrong password) — callers must not
    distinguish the two in the response, to avoid confirming which emails have accounts."""
    user = session.scalar(select(UserModel).where(UserModel.email == email.strip().lower()))
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_session(session: Session, user_id: UUID) -> SessionModel:
    model = SessionModel(
        token=generate_session_token(),
        user_id=user_id,
        expires_at=datetime.now(UTC) + SESSION_LIFETIME,
    )
    session.add(model)
    session.flush()
    return model


def get_user_for_token(session: Session, token: str) -> UserModel | None:
    session_model = session.scalar(select(SessionModel).where(SessionModel.token == token))
    if session_model is None:
        return None
    if session_model.expires_at < datetime.now(UTC):
        return None
    return session.get(UserModel, session_model.user_id)


def delete_session(session: Session, token: str) -> None:
    session_model = session.get(SessionModel, token)
    if session_model is not None:
        session.delete(session_model)
