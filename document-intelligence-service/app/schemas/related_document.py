"""Pydantic schemas for related document requests and responses."""

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import RelatedDocumentType


class RelatedDocumentCreateRequest(BaseModel):
    """Payload for creating a directional relationship between two documents."""

    related_document_id: uuid.UUID = Field(
        ...,
        description="Target document UUID to associate with source document",
    )
    relationship_type: RelatedDocumentType = Field(
        default=RelatedDocumentType.ANSWER_KEY,
        description="Functional relationship type (e.g., ANSWER_KEY)",
    )


class RelatedDocumentResponse(BaseModel):
    """Representation of an established document-to-document relationship."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    related_document_id: uuid.UUID
    relationship_type: RelatedDocumentType
    created_at: datetime.datetime


class RelatedDocumentListResponse(BaseModel):
    """Collection of related document relationships for a source document."""

    document_id: uuid.UUID
    total: int
    items: list[RelatedDocumentResponse]
