"""DocumentPage domain model preserving page-level OCR and layout state."""

import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.document import Document
    from app.db.models.question import QuestionSource


class DocumentPage(Base):
    """DocumentPage entity storing page text, OCR metadata, and orientation."""

    __tablename__ = "document_pages"

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
    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    text_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    ocr_used: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )
    ocr_confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    rotation: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("page_number > 0", name="chk_page_number_positive"),
        CheckConstraint(
            "ocr_confidence IS NULL OR (ocr_confidence >= 0.0 AND ocr_confidence <= 1.0)",
            name="chk_ocr_confidence_range",
        ),
        UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),
        Index("ix_document_pages_doc_page", "document_id", "page_number"),
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="pages")
    question_sources: Mapped[list["QuestionSource"]] = relationship(
        "QuestionSource",
        back_populates="document_page",
        cascade="all, delete-orphan",
    )
