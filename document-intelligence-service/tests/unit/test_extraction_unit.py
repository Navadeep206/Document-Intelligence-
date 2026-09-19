"""Unit tests for question extraction, boundary detection, option parsing, and classification."""

import pytest

from app.db.models.enums import QuestionType
from app.services.extraction.models import ExtractedOption
from app.services.extraction.option_parser import option_parser
from app.services.extraction.question_boundary_detector import question_boundary_detector
from app.services.extraction.question_type_classifier import question_type_classifier


def test_classify_mcq_from_options() -> None:
    options = [
        ExtractedOption(label="A", text="Option A", position=1),
        ExtractedOption(label="B", text="Option B", position=2),
        ExtractedOption(label="C", text="Option C", position=3),
        ExtractedOption(label="D", text="Option D", position=4),
    ]
    q_type = question_type_classifier.classify("What is the capital of France?", options)
    assert q_type == QuestionType.MCQ


def test_classify_true_false_from_options() -> None:
    options = [
        ExtractedOption(label="A", text="True", position=1),
        ExtractedOption(label="B", text="False", position=2),
    ]
    q_type = question_type_classifier.classify("The earth is flat.", options)
    assert q_type == QuestionType.TRUE_FALSE


def test_classify_true_false_from_stem() -> None:
    q_type = question_type_classifier.classify("State whether true or false: Photosynthesis produces oxygen.", [])
    assert q_type == QuestionType.TRUE_FALSE


def test_classify_numerical() -> None:
    q_type = question_type_classifier.classify("Calculate the velocity of an electron given its kinetic energy.", [])
    assert q_type == QuestionType.NUMERICAL


def test_classify_long_answer() -> None:
    q_type = question_type_classifier.classify("Explain the process of cellular respiration in detail with a diagram.", [])
    assert q_type == QuestionType.LONG_ANSWER


def test_classify_short_answer() -> None:
    q_type = question_type_classifier.classify("Define what is meant by momentum in classical physics.", [])
    assert q_type == QuestionType.SHORT_ANSWER


def test_parse_vertical_options() -> None:
    lines = [
        "Which planet is known as the Red Planet?",
        "A. Venus",
        "B. Mars",
        "C. Jupiter",
        "D. Saturn",
    ]
    stem, options = option_parser.parse_options(lines)
    assert "Red Planet" in stem
    assert len(options) == 4
    assert options[0].label == "A"
    assert options[0].text == "Venus"
    assert options[1].label == "B"
    assert options[1].text == "Mars"
    assert options[2].label == "C"
    assert options[3].label == "D"


def test_parse_inline_options() -> None:
    lines = [
        "Select the primary database used in this architecture:",
        "(A) MySQL   (B) PostgreSQL   (C) MongoDB   (D) SQLite",
    ]
    stem, options = option_parser.parse_options(lines)
    assert "primary database" in stem
    assert len(options) == 4
    assert options[0].label == "A"
    assert "PostgreSQL" in [opt.text for opt in options]


def test_parse_options_with_parenthesis_numbering() -> None:
    lines = [
        "What is 2 + 2?",
        "[1] 3",
        "[2] 4",
        "[3] 5",
    ]
    stem, options = option_parser.parse_options(lines)
    assert len(options) == 3
    assert options[0].label == "1"
    assert options[1].text == "4"


def test_boundary_detection_multiple_numbering_styles() -> None:
    test_cases = [
        ("1. First question on physics?", "1"),
        ("Q.2 Second question on chemistry?", "2"),
        ("Question 3: Third question on biology?", "3"),
        ("(4) Fourth question on math?", "4"),
    ]
    for line, expected_num in test_cases:
        boundary = question_boundary_detector.evaluate_line(line, line_idx=0)
        assert boundary is not None, f"Failed to detect boundary for {line}"
        assert boundary.question_number == expected_num
        assert boundary.score >= 0.25


def test_boundary_detection_filters_headings() -> None:
    heading_lines = [
        "SECTION A - GENERAL KNOWLEDGE",
        "INSTRUCTIONS: Answer all questions.",
        "PART I: PHYSICS",
    ]
    for line in heading_lines:
        boundary = question_boundary_detector.evaluate_line(line, line_idx=0)
        assert boundary is None, f"Expected heading to be filtered out: {line}"
