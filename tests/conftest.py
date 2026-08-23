import os
import uuid
from collections.abc import Callable, Generator

import pytest
from app.auth.security import hash_password
from app.db.models import UserModel
from app.db.session import get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_STAFF_LOGIN_PASSWORD = "test reader password"


@pytest.fixture
def login_as_staff() -> Callable[[TestClient, Session], UserModel]:
    """Callable fixture: `login_as_staff(db_client, postgres_session)` creates a throwaway
    internal-staff user and logs `db_client` into it via a real `POST /api/v1/auth/login`,
    returning the created row. Factored out of the several near-identical `_seed_and_login`
    helpers already duplicated per test file (`test_dataset_deletion.py`,
    `test_finding_feedback.py`) so tests that only need "any authenticated session" — e.g. the
    now-authenticated `GET /api/v1/datasets`/`GET /api/v1/findings/{id}/feedback` reads,
    `TASK-037` Code Reviewer findings 1/2 — don't hand-roll it again.
    """

    def _login(client: TestClient, session: Session) -> UserModel:
        user = UserModel(
            email=f"reader-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password(_STAFF_LOGIN_PASSWORD),
            display_name="Test Reader",
        )
        session.add(user)
        session.commit()
        response = client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": _STAFF_LOGIN_PASSWORD},
        )
        assert response.status_code == 200
        return user

    return _login


@pytest.fixture
def postgres_session() -> Generator[Session, None, None]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
        session.rollback()


@pytest.fixture
def db_client(postgres_session: Session) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield postgres_session

    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
