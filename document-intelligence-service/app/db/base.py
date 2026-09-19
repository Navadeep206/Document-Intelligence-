"""Declarative base class for all SQLAlchemy domain models."""

from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """Base class for all persistent domain entities in SQLAlchemy 2.x."""

    @declared_attr.directive
    def __tablename__(cls) -> str:
        # Default table naming convention based on class name
        return cls.__name__.lower()
