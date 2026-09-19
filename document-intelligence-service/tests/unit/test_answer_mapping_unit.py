"""Unit tests for answer key parsing and question-answer matching strategies."""

import uuid
import pytest

from app.db.models.enums import QuestionStatus, QuestionType
from app.db.models.question import Question
from app.services.answer_extraction.answer_matcher import answer_matcher
from app.services.answer_extraction.answer_parser import answer_parser


def make_question(number: str, text: str = "Test question") -> Question:
    return Question(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        question_number=number,
        question_text=text,
        question_type=QuestionType.MCQ,
        status=QuestionStatus.EXTRACTED,
    )


def test_parse_single_line_answer() -> None:
    entries = answer_parser.parse_line("1. A", page_number=1)
    assert len(entries) == 1
    assert entries[0].question_reference == "1"
    assert entries[0].normalized_reference == "1"
    assert entries[0].answer_value == "A"
    assert not entries[0].is_uncertain


def test_parse_grid_format_answers() -> None:
    line = "1. B   2. C   3. A   4. D"
    entries = answer_parser.parse_line(line, page_number=2)
    assert len(entries) == 4
    assert entries[0].normalized_reference == "1"
    assert entries[0].answer_value == "B"
    assert entries[3].normalized_reference == "4"
    assert entries[3].answer_value == "D"


def test_parse_case_and_prefix_normalization() -> None:
    assert answer_parser.normalize_reference("Q.15") == "15"
    assert answer_parser.normalize_reference("Question 07") == "7"
    assert answer_parser.normalize_reference("12)") == "12"
    assert answer_parser.normalize_reference("Question No. 4") == "4"


def test_parse_uncertain_answer_marker() -> None:
    entries = answer_parser.parse_line("5. ?", page_number=1)
    assert len(entries) == 1
    assert entries[0].is_uncertain is True

    entries_unclear = answer_parser.parse_line("6. unclear", page_number=1)
    assert len(entries_unclear) == 1
    assert entries_unclear[0].is_uncertain is True


def test_exact_unique_match() -> None:
    q1 = make_question("1")
    q2 = make_question("2")
    entries = answer_parser.parse_line("1. C")

    results = answer_matcher.match_answers(entries, [q1, q2])
    assert len(results) == 1
    assert results[0].matched_question_id == q1.id
    assert results[0].match_strategy == "EXACT"
    assert results[0].confidence > 0.90


def test_normalized_reference_match() -> None:
    from app.services.answer_extraction.answer_models import ParsedAnswerEntry
    q15 = make_question("15")
    # Raw reference "Q.15" vs question_number "15" -> strategy is NORMALIZED
    entry = ParsedAnswerEntry(
        question_reference="Q.15",
        normalized_reference="15",
        answer_value="B",
    )

    results = answer_matcher.match_answers([entry], [q15])
    assert len(results) == 1
    assert results[0].matched_question_id == q15.id
    assert results[0].match_strategy == "NORMALIZED"


def test_unmatched_answer_when_question_missing() -> None:
    q1 = make_question("1")
    entries = answer_parser.parse_line("99. A")

    results = answer_matcher.match_answers(entries, [q1])
    assert len(results) == 1
    assert results[0].matched_question_id is None
    assert results[0].match_strategy == "UNMATCHED"


def test_ambiguous_match_on_duplicate_question_numbers() -> None:
    q1_a = make_question("1", "Section A question 1")
    q1_b = make_question("1", "Section B question 1")
    entries = answer_parser.parse_line("1. A")

    results = answer_matcher.match_answers(entries, [q1_a, q1_b])
    assert len(results) == 1
    assert results[0].matched_question_id is None
    assert results[0].match_strategy == "AMBIGUOUS"
    assert "Ambiguous" in results[0].notes[0]


def test_uncertain_answer_not_assigned_to_question() -> None:
    q1 = make_question("1")
    entries = answer_parser.parse_line("1. ?")

    results = answer_matcher.match_answers(entries, [q1])
    assert len(results) == 1
    assert results[0].matched_question_id is None
    assert results[0].match_strategy == "UNCERTAIN"
