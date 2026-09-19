"""Internal data transfer objects (DTOs) for question extraction."""

from dataclasses import dataclass, field
from typing import Optional
import uuid

from app.db.models.enums import QuestionStatus, QuestionType


@dataclass
class ExtractedOption:
    """Represents an extracted multiple-choice option."""

    label: str  # e.g., "A", "B", "(a)", "1"
    text: str  # Option textual content stripped of label
    position: int  # 1-indexed sequential position (1, 2, 3...)


@dataclass
class ExtractedQuestion:
    """Intermediate representation of an extracted examination question."""

    question_number: Optional[str]  # e.g., "1", "Q1", "12", or None
    question_text: str  # Clean question stem stripped of options
    question_type: QuestionType = QuestionType.UNKNOWN
    options: list[ExtractedOption] = field(default_factory=list)
    source_pages: list[tuple[int, uuid.UUID]] = field(default_factory=list)  # [(page_number, document_page_id), ...]
    raw_text: str = ""
    status: QuestionStatus = QuestionStatus.EXTRACTED
    is_valid: bool = True
    validation_notes: list[str] = field(default_factory=list)


@dataclass
class DocumentExtractionResult:
    """Summary result of question extraction across all document pages."""

    document_id: uuid.UUID
    questions: list[ExtractedQuestion] = field(default_factory=list)
    total_questions: int = 0
    total_pages_processed: int = 0
