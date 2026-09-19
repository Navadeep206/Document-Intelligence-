"""Pydantic schemas for request validation and API serialization."""

from app.schemas.answer import (
    AnswerKeyResponse,
    AnswerKeySummaryResponse,
    AnswerMappingResponse,
    DocumentAnswersResponse,
)
from app.schemas.auth import TokenResponse, UserLogin, UserRegister, UserResponse
from app.schemas.document import (
    DocumentListResponse,
    DocumentPageListResponse,
    DocumentPageResponse,
    DocumentProcessingStatusResponse,
    DocumentResponse,
    DocumentUploadAcceptedResponse,
    DocumentUploadResponse,
    ProcessingJobResponse,
)
from app.schemas.question import (
    QuestionListResponse,
    QuestionOptionResponse,
    QuestionResponse,
    QuestionSourceResponse,
)
from app.schemas.related_document import (
    RelatedDocumentCreateRequest,
    RelatedDocumentListResponse,
    RelatedDocumentResponse,
)
from app.schemas.review import (
    DocumentReviewSummaryResponse,
    ReviewItemListResponse,
    ReviewItemResponse,
    ReviewItemUpdate,
)

__all__ = [
    "UserRegister",
    "UserLogin",
    "UserResponse",
    "TokenResponse",
    "DocumentUploadResponse",
    "DocumentUploadAcceptedResponse",
    "DocumentResponse",
    "DocumentListResponse",
    "ProcessingJobResponse",
    "DocumentProcessingStatusResponse",
    "DocumentPageResponse",
    "DocumentPageListResponse",
    "QuestionOptionResponse",
    "QuestionSourceResponse",
    "QuestionResponse",
    "QuestionListResponse",
    "AnswerKeyResponse",
    "AnswerMappingResponse",
    "DocumentAnswersResponse",
    "AnswerKeySummaryResponse",
    "RelatedDocumentCreateRequest",
    "RelatedDocumentResponse",
    "RelatedDocumentListResponse",
    "ReviewItemResponse",
    "ReviewItemListResponse",
    "ReviewItemUpdate",
    "DocumentReviewSummaryResponse",
]
