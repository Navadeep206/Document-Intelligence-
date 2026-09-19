"""RelatedDocument domain model linking interrelated examination documents."""

import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import RelatedDocumentType

if TYPE_CHECKING:
    from app.db.models.document import Document


class RelatedDocument(Base):
    """RelatedDocument entity modeling many-to-many associations between paired documents."""

    __tablename__ = "related_documents"

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
    related_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[RelatedDocumentType] = mapped_column(
        Enum(
            RelatedDocumentType,
            name="related_document_type_enum",
            native_enum=True,
        ),
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "document_id != related_document_id",
            name="chk_related_document_no_self_ref",
        ),
        UniqueConstraint(
            "document_id",
            "related_document_id",
            "relationship_type",
            name="uq_related_document_pair_type",
        ),
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        foreign_keys=[document_id],
        back_populates="related_documents",
    )
    related_document: Mapped["Document"] = relationship(
        "Document",
        foreign_keys=[related_document_id],
        back_populates="inverse_related_documents",
    )
