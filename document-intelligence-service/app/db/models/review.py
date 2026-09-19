"""ReviewItem domain model for human-in-the-loop review workflows."""

import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import ReviewSeverity, ReviewStatus

if TYPE_CHECKING:
    from app.db.models.document import Document
    from app.db.models.page import DocumentPage
    from app.db.models.question import Question


class ReviewItem(Base):
    """ReviewItem entity capturing extraction uncertainties for human triage."""

    __tablename__ = "review_items"

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
    question_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    severity: Mapped[ReviewSeverity] = mapped_column(
        Enum(ReviewSeverity, name="review_severity_enum", native_enum=True),
        default=ReviewSeverity.MEDIUM,
        server_default=ReviewSeverity.MEDIUM.value,
        nullable=False,
        index=True,
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status_enum", native_enum=True),
        default=ReviewStatus.OPEN,
        server_default=ReviewStatus.OPEN.value,
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    details: Mapped[Optional[str]] = mapped_column(
        Text,
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
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="chk_review_item_confidence_range",
        ),
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document", back_populates="review_items"
    )
    question: Mapped[Optional["Question"]] = relationship(
        "Question", back_populates="review_items"
    )
    page: Mapped[Optional["DocumentPage"]] = relationship("DocumentPage")
