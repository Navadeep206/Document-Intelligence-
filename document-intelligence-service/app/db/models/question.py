"""Question, QuestionOption, and QuestionSource domain models."""

import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import AnswerSource, QuestionStatus, QuestionType

if TYPE_CHECKING:
    from app.db.models.answer import AnswerMapping
    from app.db.models.document import Document
    from app.db.models.page import DocumentPage
    from app.db.models.review import ReviewItem


class Question(Base):
    """Question entity representing an extracted examination question."""

    __tablename__ = "questions"

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
    question_number: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    question_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, name="question_type_enum", native_enum=True),
        default=QuestionType.UNKNOWN,
        server_default=QuestionType.UNKNOWN.value,
        nullable=False,
        index=True,
    )
    status: Mapped[QuestionStatus] = mapped_column(
        Enum(QuestionStatus, name="question_status_enum", native_enum=True),
        default=QuestionStatus.EXTRACTED,
        server_default=QuestionStatus.EXTRACTED.value,
        nullable=False,
        index=True,
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    answer: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    answer_confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    answer_source: Mapped[Optional[AnswerSource]] = mapped_column(
        Enum(AnswerSource, name="answer_source_enum", native_enum=True),
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
            name="chk_question_confidence_range",
        ),
        CheckConstraint(
            "answer_confidence IS NULL OR (answer_confidence >= 0.0 AND answer_confidence <= 1.0)",
            name="chk_question_answer_confidence_range",
        ),
        Index("ix_questions_doc_qnum", "document_id", "question_number"),
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="questions")
    options: Mapped[list["QuestionOption"]] = relationship(
        "QuestionOption",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionOption.position",
    )
    sources: Mapped[list["QuestionSource"]] = relationship(
        "QuestionSource",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionSource.page_sequence",
    )
    review_items: Mapped[list["ReviewItem"]] = relationship(
        "ReviewItem",
        back_populates="question",
        cascade="all, delete-orphan",
    )
    answer_mappings: Mapped[list["AnswerMapping"]] = relationship(
        "AnswerMapping",
        back_populates="question",
    )

    @property
    def review_required(self) -> bool:
        """Indicate whether the question requires human review."""
        if self.status in (QuestionStatus.REVIEW_REQUIRED, QuestionStatus.PARTIAL):
            return True
        if "review_items" in self.__dict__ and self.review_items:
            from app.db.models.enums import ReviewStatus
            return any(item.status == ReviewStatus.OPEN for item in self.review_items)
        return False

    @property
    def review_count(self) -> int:
        """Count of active open review items for this question."""
        if "review_items" in self.__dict__ and self.review_items:
            from app.db.models.enums import ReviewStatus
            return sum(1 for item in self.review_items if item.status == ReviewStatus.OPEN)
        return 0


class QuestionOption(Base):
    """QuestionOption entity representing choices for multiple choice questions."""

    __tablename__ = "question_options"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    option_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("position > 0", name="chk_question_option_position_positive"),
        UniqueConstraint("question_id", "label", name="uq_question_option_label"),
        UniqueConstraint("question_id", "position", name="uq_question_option_position"),
    )

    # Relationships
    question: Mapped["Question"] = relationship("Question", back_populates="options")


class QuestionSource(Base):
    """QuestionSource entity preserving provenance links between questions and pages."""

    __tablename__ = "question_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_sequence: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "page_sequence > 0",
            name="chk_question_source_page_sequence_positive",
        ),
        UniqueConstraint(
            "question_id", "document_page_id", name="uq_question_source_page"
        ),
    )

    # Relationships
    question: Mapped["Question"] = relationship("Question", back_populates="sources")
    document_page: Mapped["DocumentPage"] = relationship(
        "DocumentPage", back_populates="question_sources"
    )
