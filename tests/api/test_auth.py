from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.auth.dependencies import SESSION_COOKIE_NAME
from app.auth.security import hash_password
from app.db.models import SessionModel, UserModel
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _seed_user(session: Session, *, password: str = "correct horse battery staple") -> UserModel:
    user = UserModel(
        email=f"reviewer-{uuid4().hex}@example.com",
        password_hash=hash_password(password),
        display_name="Test Reviewer",
    )
    session.add(user)
    session.flush()
    session.commit()
    return user


def test_login_succeeds_and_sets_a_session_cookie(
    db_client: TestClient, postgres_session: Session
) -> None:
    user = _seed_user(postgres_session, password="a real password 123")

    response = db_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "a real password 123"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == user.email
    assert SESSION_COOKIE_NAME in response.cookies


def test_login_rejects_wrong_password_with_a_generic_message(
    db_client: TestClient, postgres_session: Session
) -> None:
    user = _seed_user(postgres_session, password="the real password")

    response = db_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "wrong password"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_unknown_email_with_the_same_generic_message(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "does not matter"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_me_requires_authentication(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_returns_the_logged_in_user(db_client: TestClient, postgres_session: Session) -> None:
    user = _seed_user(postgres_session, password="another real password")
    db_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "another real password"}
    )

    response = db_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


def test_logout_invalidates_the_session(db_client: TestClient, postgres_session: Session) -> None:
    user = _seed_user(postgres_session, password="logout password 123")
    db_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "logout password 123"}
    )
    assert db_client.get("/api/v1/auth/me").status_code == 200

    logout_response = db_client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204

    assert db_client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected(db_client: TestClient, postgres_session: Session) -> None:
    user = _seed_user(postgres_session)
    expired = SessionModel(
        token=f"expired-token-for-test-{uuid4().hex}",
        user_id=user.id,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    postgres_session.add(expired)
    postgres_session.commit()

    db_client.cookies.set(SESSION_COOKIE_NAME, expired.token)
    response = db_client.get("/api/v1/auth/me")

    assert response.status_code == 401
