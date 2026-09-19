"""Database connectivity, engine initialization, session factory, and health checks."""

from collections.abc import Generator
import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger("document-intelligence-service")

settings = get_settings()


def create_db_engine(url: str, echo: bool = False) -> Engine:
    """Create a configured SQLAlchemy engine with connection pooling."""
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        return create_engine(url, echo=echo, connect_args=connect_args)

    return create_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,
        connect_args=connect_args,
    )


engine: Engine = create_db_engine(settings.DATABASE_URL, echo=settings.DEBUG)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding isolated database sessions."""
    db: Session = SessionLocal()
    try:
        yield db
    except Exception as exc:
        db.rollback()
        logger.error("Database session transaction rolled back due to error: %s", exc)
        raise
    finally:
        db.close()


def check_db_health() -> tuple[bool, str]:
    """Execute a lightweight probe to verify database reachability."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "healthy"
    except SQLAlchemyError as exc:
        logger.error("Database health check probe failed: %s", exc)
        return False, "unhealthy"
    except Exception as exc:
        logger.error("Unexpected error during database health probe: %s", exc)
        return False, "unhealthy"
