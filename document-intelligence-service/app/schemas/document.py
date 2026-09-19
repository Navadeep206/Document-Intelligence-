"""Document request and response schemas."""

import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import DocumentRole, DocumentStatus, DocumentType


class DocumentUploadResponse(BaseModel):
    """Immediate response schema returned upon successful document upload (HTTP 201)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    document_type: DocumentType
    document_role: DocumentRole
    file_size: int
    status: DocumentStatus
    created_at: datetime.datetime


class DocumentResponse(BaseModel):
    """Detailed document metadata representation for retrieval (storage_path is masked)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    document_type: DocumentType
    document_role: DocumentRole
    file_size: int
    status: DocumentStatus
    page_count: Optional[int] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class DocumentListResponse(BaseModel):
    """Paginated collection of user-owned documents."""

    items: list[DocumentResponse]
    page: int = Field(ge=1, description="Current page index")
    page_size: int = Field(ge=1, le=100, description="Items per page")
    total: int = Field(ge=0, description="Total document count matching query")


class DocumentUploadAcceptedResponse(BaseModel):
    """Response returned upon accepting document for asynchronous extraction (HTTP 202)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: DocumentStatus
    job_id: uuid.UUID
    created_at: datetime.datetime


class ProcessingJobResponse(BaseModel):
    """Processing job state, execution attempt, and worker tracking details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    attempt: int
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime.datetime
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None


class DocumentProcessingStatusResponse(BaseModel):
    """Real-time processing status response for polling and client progress tracking."""

    document_id: uuid.UUID
    document_status: DocumentStatus
    page_count: Optional[int] = None
    job: Optional[ProcessingJobResponse] = None


class DocumentPageResponse(BaseModel):
    """Extracted page text and OCR telemetry representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    text_content: Optional[str] = None
    ocr_used: Optional[bool] = None
    ocr_confidence: Optional[float] = None
    rotation: Optional[int] = None
    created_at: datetime.datetime


class DocumentPageListResponse(BaseModel):
    """Collection of extracted pages for an authorized document."""

    document_id: uuid.UUID
    total_pages: int
    items: list[DocumentPageResponse]

