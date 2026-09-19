"""Document domain model for ingested examination files."""

import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import DocumentRole, DocumentStatus, DocumentType

if TYPE_CHECKING:
    from app.db.models.answer import AnswerKey
    from app.db.models.page import DocumentPage
    from app.db.models.processing_job import ProcessingJob
    from app.db.models.question import Question
    from app.db.models.related_document import RelatedDocument
    from app.db.models.review import ReviewItem
    from app.db.models.user import User


class Document(Base):
    """Document entity storing file metadata and extraction lifecycle state."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type_enum", native_enum=True),
        nullable=False,
    )
    document_role: Mapped[DocumentRole] = mapped_column(
        Enum(DocumentRole, name="document_role_enum", native_enum=True),
        default=DocumentRole.UNKNOWN,
        server_default=DocumentRole.UNKNOWN.value,
        nullable=False,
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    page_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status_enum", native_enum=True),
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.value,
        nullable=False,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    processed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("file_size > 0", name="chk_document_file_size_positive"),
        CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="chk_document_page_count_non_negative",
        ),
        Index("ix_documents_owner_status", "owner_id", "status"),
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="documents")
    pages: Mapped[list["DocumentPage"]] = relationship(
        "DocumentPage",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentPage.page_number",
    )
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(
        "ProcessingJob",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ProcessingJob.created_at.desc()",
    )
    questions: Mapped[list["Question"]] = relationship(
        "Question",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    answer_keys: Mapped[list["AnswerKey"]] = relationship(
        "AnswerKey",
        foreign_keys="[AnswerKey.document_id]",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    source_answer_keys: Mapped[list["AnswerKey"]] = relationship(
        "AnswerKey",
        foreign_keys="[AnswerKey.source_document_id]",
        back_populates="source_document",
    )
    review_items: Mapped[list["ReviewItem"]] = relationship(
        "ReviewItem",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    related_documents: Mapped[list["RelatedDocument"]] = relationship(
        "RelatedDocument",
        foreign_keys="[RelatedDocument.document_id]",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    inverse_related_documents: Mapped[list["RelatedDocument"]] = relationship(
        "RelatedDocument",
        foreign_keys="[RelatedDocument.related_document_id]",
        back_populates="related_document",
        cascade="all, delete-orphan",
    )
