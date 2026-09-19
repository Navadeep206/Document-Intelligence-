"""Internal data transfer objects (DTOs) for answer-key extraction and matching."""

from dataclasses import dataclass, field
from typing import Optional
import uuid


@dataclass
class ParsedAnswerEntry:
    """Represents an individual extracted answer-key entry."""

    question_reference: str  # e.g., "1", "Q1", "15", "12)"
    normalized_reference: str  # e.g., "1", "15", "12"
    answer_value: str  # e.g., "B", "True", "42", "A, C", "3.14"
    source_page: Optional[int] = None  # 1-indexed page number
    confidence: float = 1.0
    is_uncertain: bool = False
    raw_text: str = ""


@dataclass
class AnswerSection:
    """Identified answer-key section metadata and extracted text lines."""

    source_page_start: int
    source_page_end: int
    header_text: str
    format_description: str
    lines: list[tuple[int, str]] = field(default_factory=list)  # [(page_number, line_text), ...]


@dataclass
class MatchResult:
    """Association decision linking a parsed answer entry to a Question entity."""

    entry: ParsedAnswerEntry
    matched_question_id: Optional[uuid.UUID] = None
    confidence: float = 0.0
    match_strategy: str = "UNMATCHED"  # "EXACT", "NORMALIZED", "UNMATCHED", "UNCERTAIN"
    notes: list[str] = field(default_factory=list)


@dataclass
class AnswerExtractionResult:
    """Comprehensive summary of answer-key detection, extraction, and question matching."""

    document_id: uuid.UUID
    source_document_id: uuid.UUID
    answer_key_id: Optional[uuid.UUID] = None
    total_entries: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    overall_confidence: float = 0.0
    matches: list[MatchResult] = field(default_factory=list)
