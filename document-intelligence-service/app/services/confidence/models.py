"""Data models and reason definitions for the Confidence Engine and Human Review System."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional
import uuid

from app.db.models.enums import QuestionStatus, ReviewSeverity


class ReviewReasonCode(str, Enum):
    """Standardized machine-readable review reason codes."""

    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    CORRUPTED_TEXT = "CORRUPTED_TEXT"
    INCOMPLETE_QUESTION = "INCOMPLETE_QUESTION"
    MISSING_QUESTION_NUMBER = "MISSING_QUESTION_NUMBER"
    AMBIGUOUS_QUESTION_BOUNDARY = "AMBIGUOUS_QUESTION_BOUNDARY"
    INCOMPLETE_OPTIONS = "INCOMPLETE_OPTIONS"
    MISSING_OPTION = "MISSING_OPTION"
    MULTI_PAGE_UNCERTAINTY = "MULTI_PAGE_UNCERTAINTY"
    MISSING_SOURCE_REFERENCE = "MISSING_SOURCE_REFERENCE"
    UNMATCHED_ANSWER = "UNMATCHED_ANSWER"
    AMBIGUOUS_ANSWER = "AMBIGUOUS_ANSWER"
    CONFLICTING_ANSWER = "CONFLICTING_ANSWER"
    LOW_OVERALL_CONFIDENCE = "LOW_OVERALL_CONFIDENCE"


@dataclass
class ConfidenceSignals:
    """Measurable engineering signal metrics for an extracted question."""

    ocr_quality: float
    question_text_quality: float
    boundary_confidence: float
    question_number_confidence: float
    option_completeness: float
    source_traceability: float
    page_continuity: float
    answer_mapping: float

    def to_dict(self) -> dict[str, float]:
        """Convert signals to dictionary rounded to 4 decimal places."""
        return {k: round(v, 4) for k, v in asdict(self).items()}


@dataclass
class ReviewItemSpec:
    """Specification for an actionable human review issue."""

    reason: str
    severity: ReviewSeverity
    details: str
    confidence: Optional[float] = None
    question_id: Optional[uuid.UUID] = None
    page_id: Optional[uuid.UUID] = None


@dataclass
class ConfidenceResult:
    """Complete, explainable confidence evaluation for an extracted question."""

    overall_confidence: float
    status: QuestionStatus
    signals: ConfidenceSignals
    review_required: bool
    reasons: list[ReviewReasonCode] = field(default_factory=list)
    review_items: list[ReviewItemSpec] = field(default_factory=list)
    field_confidence: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert evaluation result to JSON-compatible dictionary."""
        return {
            "overall_confidence": round(self.overall_confidence, 4),
            "status": self.status.value,
            "signals": self.signals.to_dict(),
            "review_required": self.review_required,
            "reasons": [r.value for r in self.reasons],
            "field_confidence": {k: round(v, 4) for k, v in self.field_confidence.items()},
        }


@dataclass
class DocumentReviewSummary:
    """Aggregated review telemetry for an entire document."""

    document_id: uuid.UUID
    total_questions: int
    high_confidence_questions: int
    partial_questions: int
    review_required_questions: int
    open_review_items: int
    resolved_review_items: int
    ignored_review_items: int
    unmatched_answers: int
    ambiguous_answers: int
