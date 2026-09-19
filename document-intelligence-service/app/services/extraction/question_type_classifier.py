"""Rule-based question type classification engine."""

import re
from typing import Sequence

from app.db.models.enums import QuestionType
from app.services.extraction.models import ExtractedOption


class QuestionTypeClassifier:
    """Classifies question type deterministically based on structural and linguistic patterns."""

    TRUE_FALSE_KEYWORDS = re.compile(
        r"\b(?:true\s+or\s+false|state\s+whether\s+true\s+or\s+false|mark\s+true\s+or\s+false|write\s+true\s+or\s+false)\b",
        re.IGNORECASE,
    )

    NUMERICAL_KEYWORDS = re.compile(
        r"\b(?:calculate|compute|find\s+the\s+value|evaluate|determine\s+the\s+value|what\s+is\s+the\s+value|how\s+many|find\s+the\s+number|estimate\s+the\s+value|solve\s+for\s+[a-z0-9]+)\b",
        re.IGNORECASE,
    )

    LONG_ANSWER_KEYWORDS = re.compile(
        r"\b(?:explain|describe|discuss|elaborate|derive|prove\s+that|illustrate|critically\s+analyze|with\s+a\s+neat\s+(?:sketch|diagram)|write\s+short\s+notes?\s+on|differentiate\s+between|distinguish\s+between|compare\s+and\s+contrast)\b",
        re.IGNORECASE,
    )

    SHORT_ANSWER_KEYWORDS = re.compile(
        r"\b(?:define|what\s+is|state\s+(?:the|any)|name\s+(?:the|any)|list\s+(?:any|the|two|three|four)|give\s+(?:an?\s+)?example|mention\s+(?:any|the)|expand\s+the\s+abbreviation)\b",
        re.IGNORECASE,
    )

    def classify(self, question_text: str, options: Sequence[ExtractedOption]) -> QuestionType:
        """Deterministically determine question type from options and question stem text."""
        cleaned_text = question_text.strip()
        opt_texts = [opt.text.strip().lower() for opt in options]

        # 1. Check True/False from options or text
        if opt_texts and set(opt_texts).issubset({"true", "false", "t", "f"}):
            return QuestionType.TRUE_FALSE

        if self.TRUE_FALSE_KEYWORDS.search(cleaned_text):
            return QuestionType.TRUE_FALSE

        # 2. Check Multiple Choice (MCQ)
        if len(options) >= 2:
            return QuestionType.MCQ

        # 3. Check Numerical question patterns (when no options are present)
        if self.NUMERICAL_KEYWORDS.search(cleaned_text):
            return QuestionType.NUMERICAL

        # 4. Check Long Answer patterns
        if self.LONG_ANSWER_KEYWORDS.search(cleaned_text):
            return QuestionType.LONG_ANSWER

        # 5. Check Short Answer patterns
        if self.SHORT_ANSWER_KEYWORDS.search(cleaned_text):
            return QuestionType.SHORT_ANSWER

        # 6. Fallback
        return QuestionType.UNKNOWN


question_type_classifier = QuestionTypeClassifier()
