"""Centralized, reusable domain enums for the Document Intelligence platform."""

from enum import Enum


class DocumentType(str, Enum):
    """Supported source file document formats."""

    PDF = "PDF"
    JPG = "JPG"
    JPEG = "JPEG"
    PNG = "PNG"


class DocumentStatus(str, Enum):
    """Lifecycle processing states of an ingested document."""

    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class DocumentRole(str, Enum):
    """Functional role of the document within an examination context."""

    QUESTION_PAPER = "QUESTION_PAPER"
    ANSWER_KEY = "ANSWER_KEY"
    UNKNOWN = "UNKNOWN"


class ProcessingJobStatus(str, Enum):
    """State machine transitions for asynchronous processing tasks."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class QuestionType(str, Enum):
    """Taxonomy of question structures extracted from documents."""

    MCQ = "MCQ"
    TRUE_FALSE = "TRUE_FALSE"
    SHORT_ANSWER = "SHORT_ANSWER"
    LONG_ANSWER = "LONG_ANSWER"
    NUMERICAL = "NUMERICAL"
    UNKNOWN = "UNKNOWN"


class QuestionStatus(str, Enum):
    """Quality and completeness state of an extracted question."""

    EXTRACTED = "EXTRACTED"
    PARTIAL = "PARTIAL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ReviewStatus(str, Enum):
    """Resolution state for questions or pages flagged for human review."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


class ReviewSeverity(str, Enum):
    """Impact level of extraction anomalies requiring human triage."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AnswerSource(str, Enum):
    """Provenance mechanism of an associated question answer."""

    EXTRACTED = "EXTRACTED"
    ANSWER_KEY = "ANSWER_KEY"
    AI_INFERRED = "AI_INFERRED"
    UNKNOWN = "UNKNOWN"


class RelatedDocumentType(str, Enum):
    """Directional relationship between paired examination documents."""

    ANSWER_KEY = "ANSWER_KEY"
    QUESTION_PAPER = "QUESTION_PAPER"
    SUPPLEMENT = "SUPPLEMENT"
    OTHER = "OTHER"
