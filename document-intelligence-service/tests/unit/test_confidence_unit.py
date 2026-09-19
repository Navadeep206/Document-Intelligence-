"""Unit tests for confidence engine calculation, weighting, and status threshold classification."""

import uuid
import pytest

from app.core.config import get_settings
from app.db.models.enums import QuestionStatus, QuestionType, ReviewSeverity
from app.db.models.page import DocumentPage
from app.db.models.question import Question, QuestionOption, QuestionSource
from app.services.confidence.confidence_engine import ConfidenceEngine
from app.services.confidence.models import ConfidenceSignals

settings = get_settings()
engine = ConfidenceEngine(settings)


def create_mock_question(
    qnum: str = "1",
    text: str = "Which of the following is an interpreted programming language?",
    options: list[tuple[str, str]] = None,
    with_source: bool = True,
    doc_id: uuid.UUID = None,
    page: DocumentPage = None,
) -> tuple[Question, dict[uuid.UUID, DocumentPage]]:
    doc_id = doc_id or uuid.uuid4()
    q_id = uuid.uuid4()
    p_id = page.id if page else uuid.uuid4()

    if not page:
        page = DocumentPage(
            id=p_id,
            document_id=doc_id,
            page_number=1,
            text_content="Page 1 sample content",
            ocr_used=False,
            ocr_confidence=0.98,
        )

    q = Question(
        id=q_id,
        document_id=doc_id,
        question_number=qnum,
        question_text=text,
        question_type=QuestionType.MCQ if options else QuestionType.SHORT_ANSWER,
        confidence=1.0,
    )

    if options:
        q.options = [
            QuestionOption(
                id=uuid.uuid4(),
                question_id=q_id,
                label=opt[0],
                option_text=opt[1],
                position=i + 1,
            )
            for i, opt in enumerate(options)
        ]
    else:
        q.options = []

    if with_source:
        q.sources = [
            QuestionSource(
                id=uuid.uuid4(),
                question_id=q_id,
                document_page_id=p_id,
                page_sequence=1,
            )
        ]
    else:
        q.sources = []

    return q, {p_id: page}


def test_confidence_weights_sum_to_one() -> None:
    total = (
        settings.CONFIDENCE_OCR_WEIGHT
        + settings.CONFIDENCE_TEXT_WEIGHT
        + settings.CONFIDENCE_BOUNDARY_WEIGHT
        + settings.CONFIDENCE_NUMBER_WEIGHT
        + settings.CONFIDENCE_OPTIONS_WEIGHT
        + settings.CONFIDENCE_SOURCE_WEIGHT
        + settings.CONFIDENCE_PAGE_WEIGHT
        + settings.CONFIDENCE_ANSWER_WEIGHT
    )
    assert abs(total - 1.0) < 1e-4


def test_high_confidence_classification() -> None:
    q, pages = create_mock_question(
        options=[("A", "C"), ("B", "Python"), ("C", "Assembly"), ("D", "Rust")]
    )
    result = engine.evaluate_question(
        question=q,
        pages_by_id=pages,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=False,
    )
    assert result.overall_confidence >= 0.85
    assert result.status == QuestionStatus.EXTRACTED
    assert result.review_required is False


def test_medium_confidence_partial_classification() -> None:
    page = DocumentPage(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        page_number=1,
        text_content="Page 1 sample content",
        ocr_used=True,
        ocr_confidence=0.55,
    )
    # Moderate OCR + missing options in MCQ causes deductions into PARTIAL
    q, pages = create_mock_question(
        options=[("A", "C")],
        page=page,
    )
    result = engine.evaluate_question(
        question=q,
        pages_by_id=pages,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=False,
    )
    # Deductions should bring score into PARTIAL [0.60, 0.85)
    assert 0.60 <= result.overall_confidence < 0.85
    assert result.status == QuestionStatus.PARTIAL


def test_low_confidence_missing_sources_and_number() -> None:
    # Question with no question number, no source pages, very short text
    page = DocumentPage(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        page_number=1,
        ocr_used=True,
        ocr_confidence=0.30,  # Very low OCR
    )
    q, pages = create_mock_question(
        qnum=None,
        text="Abc?",
        options=[],
        with_source=False,
        page=page,
    )
    result = engine.evaluate_question(
        question=q,
        pages_by_id=pages,
        duplicate_numbers_in_doc=set(),
    )
    assert result.overall_confidence < 0.60
    assert result.status == QuestionStatus.REVIEW_REQUIRED
    assert result.review_required is True
    assert len(result.review_items) > 0


def test_boundary_condition_thresholds() -> None:
    # Verify thresholds logic directly
    assert settings.CONFIDENCE_THRESHOLD_EXTRACTED == 0.85
    assert settings.CONFIDENCE_THRESHOLD_PARTIAL == 0.60
    assert settings.CONFIDENCE_THRESHOLD_PARTIAL < settings.CONFIDENCE_THRESHOLD_EXTRACTED
