"""AnswerKey and AnswerMapping domain models for answer reconciliation."""

import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.document import Document
    from app.db.models.question import Question


class AnswerKey(Base):
    """AnswerKey entity representing answer schedules linked to question documents."""

    __tablename__ = "answer_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    format_description: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="chk_answer_key_confidence_range",
        ),
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        foreign_keys=[document_id],
        back_populates="answer_keys",
    )
    source_document: Mapped[Optional["Document"]] = relationship(
        "Document",
        foreign_keys=[source_document_id],
        back_populates="source_answer_keys",
    )
    mappings: Mapped[list["AnswerMapping"]] = relationship(
        "AnswerMapping",
        back_populates="answer_key",
        cascade="all, delete-orphan",
    )


class AnswerMapping(Base):
    """AnswerMapping entity linking an answer-key entry to an extracted question."""

    __tablename__ = "answer_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    answer_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answer_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    answer_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    source_page: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="chk_answer_mapping_confidence_range",
        ),
        CheckConstraint(
            "source_page IS NULL OR source_page > 0",
            name="chk_answer_mapping_source_page_positive",
        ),
    )

    # Relationships
    answer_key: Mapped["AnswerKey"] = relationship(
        "AnswerKey", back_populates="mappings"
    )
    question: Mapped[Optional["Question"]] = relationship(
        "Question", back_populates="answer_mappings"
    )
