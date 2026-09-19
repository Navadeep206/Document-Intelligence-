"""Authentication and authorization test suite."""

from datetime import timedelta
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.db.database import SessionLocal
from app.db.models.user import User
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_register_user_success(db: Session) -> None:
    """Test standard user registration returns 201 and excludes password hashes."""
    unique_email = f"register_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": unique_email,
        "password": "StrongPassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["email"] == unique_email
    assert data["is_active"] is True
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data

    # Verify user in database has Argon2 password hash
    user = db.scalar(select(User).where(User.email == unique_email))
    assert user is not None
    assert user.password_hash != "StrongPassword123!"
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password("StrongPassword123!", user.password_hash)


def test_register_duplicate_email_rejected() -> None:
    """Test that registering an existing email returns 400."""
    unique_email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    payload = {"email": unique_email, "password": "StrongPassword123!"}

    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 400
    assert "EMAIL_ALREADY_REGISTERED" in res2.text


def test_login_successful() -> None:
    """Test login with correct credentials returns a signed JWT token."""
    email = f"login_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})

    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200

    data = login_resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


def test_login_wrong_password() -> None:
    """Test login with incorrect password returns 401."""
    email = f"wrongpw_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword999!"})
    assert resp.status_code == 401
    assert "INVALID_CREDENTIALS" in resp.text


def test_login_unknown_email() -> None:
    """Test login with non-existent email returns 401 without revealing presence."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent_9999@example.com", "password": "SomePassword123!"},
    )
    assert resp.status_code == 401
    assert "INVALID_CREDENTIALS" in resp.text


def test_access_me_protected_endpoint_success() -> None:
    """Test accessing /api/v1/auth/me with valid Bearer token."""
    email = f"me_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]

    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


def test_access_protected_without_token() -> None:
    """Test accessing protected route without Authorization header returns 401."""
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_access_protected_with_invalid_token() -> None:
    """Test accessing protected route with forged token returns 401."""
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer forged.invalid.token"},
    )
    assert resp.status_code == 401


def test_access_protected_with_expired_token() -> None:
    """Test accessing protected route with expired token returns 401."""
    expired_token = create_access_token(
        subject=str(uuid.uuid4()),
        expires_delta=timedelta(seconds=-10),
    )
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
