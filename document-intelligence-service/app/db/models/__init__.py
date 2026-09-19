"""Domain models package consolidating all entities and enums."""

from app.db.models.answer import AnswerKey, AnswerMapping
from app.db.models.document import Document
from app.db.models.enums import (
    AnswerSource,
    DocumentRole,
    DocumentStatus,
    DocumentType,
    ProcessingJobStatus,
    QuestionStatus,
    QuestionType,
    RelatedDocumentType,
    ReviewSeverity,
    ReviewStatus,
)
from app.db.models.page import DocumentPage
from app.db.models.processing_job import ProcessingJob
from app.db.models.question import Question, QuestionOption, QuestionSource
from app.db.models.related_document import RelatedDocument
from app.db.models.review import ReviewItem
from app.db.models.user import User

__all__ = [
    "User",
    "Document",
    "DocumentPage",
    "ProcessingJob",
    "Question",
    "QuestionOption",
    "QuestionSource",
    "AnswerKey",
    "AnswerMapping",
    "ReviewItem",
    "RelatedDocument",
    "DocumentType",
    "DocumentStatus",
    "DocumentRole",
    "ProcessingJobStatus",
    "QuestionType",
    "QuestionStatus",
    "ReviewStatus",
    "ReviewSeverity",
    "AnswerSource",
    "RelatedDocumentType",
]
