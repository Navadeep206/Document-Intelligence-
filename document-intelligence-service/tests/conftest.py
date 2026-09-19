"""Global pytest fixtures and configuration for hermetic, deterministic testing."""

import sqlite3
from unittest.mock import MagicMock
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
import app.db.database as db_mod
import app.db.models  # Ensure all models are registered on Base.metadata

# Create in-memory SQLite engine shared across connections
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Enforce foreign key constraints in SQLite
@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Create all schema tables
Base.metadata.create_all(bind=test_engine)

# Configure testing session factory
TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Rebind application database engine and session factory
db_mod.engine = test_engine
db_mod.SessionLocal = TestingSessionLocal

# Mock Celery delay calls by default so no Redis broker is required
from app.workers.tasks.document_processing import process_document

_orig_delay = process_document.delay

@pytest.fixture(autouse=True)
def mock_celery_delay_default(monkeypatch):
    """Ensure process_document.delay returns a valid mock task without contacting Redis."""
    def _mock_delay(*args, **kwargs):
        mock_task = MagicMock()
        mock_task.id = str(uuid.uuid4())
        return mock_task

    monkeypatch.setattr(
        "app.api.v1.documents.process_document.delay",
        _mock_delay,
    )


@pytest.fixture
def db():
    """Yield a clean test database session."""
    session = db_mod.SessionLocal()
    try:
        yield session
    finally:
        session.close()
