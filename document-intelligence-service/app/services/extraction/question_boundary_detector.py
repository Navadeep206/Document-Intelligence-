"""Scoring-based question boundary and numbering detector."""

from dataclasses import dataclass
import re
from typing import Optional


@dataclass
class DetectedBoundary:
    """Represents a candidate question start boundary with confidence score."""

    line_index: int
    question_number: Optional[str]
    score: float
    raw_line: str
    remaining_text: str


class QuestionBoundaryDetector:
    """Detects probable question starts using multi-format regexes and contextual scoring."""

    # Explicit question prefixes: Q1., Q.1, Question 1:, Question No. 1
    QUESTION_PREFIX_PATTERN = re.compile(
        r"^(?:Question\s+(?:No\.?\s*)?|Q\.?\s*)([0-9]{1,4}|[IVXLCDM]+)(?:[\.\)\:\-\–\—]|\s+)(.*)$",
        re.IGNORECASE,
    )

    # Standard numeric numbering: 1., 1), 1:, 1 -, 01., 12)
    NUMERIC_PATTERN = re.compile(
        r"^([0-9]{1,4})\s*(?:[\.\)\:\-\–\—]|\s*[\)\/])\s*(.*)$"
    )

    # Parenthesized numbers: (1), (01), (12)
    PAREN_NUMERIC_PATTERN = re.compile(
        r"^\(([0-9]{1,4})\)\s*(.*)$"
    )

    # Roman numerals: I., II., III., IV., (I), (II) (excludes single letters C and D which conflict with options)
    ROMAN_PATTERN = re.compile(
        r"^(?:(X{0,2}(?:IX|IV|V?I{1,3})|X|V)\s*(?:[\.\)\:\-\–\—]|\s*[\)\/])|(?:\((X{0,2}(?:IX|IV|V?I{1,3})|X|V)\)))\s*(.*)$",
        re.IGNORECASE,
    )

    # Question interrogative / imperative keywords
    QUESTION_START_WORDS = {
        "which", "what", "why", "how", "where", "when", "who", "whom", "whose",
        "calculate", "find", "determine", "evaluate", "compute", "estimate",
        "explain", "describe", "discuss", "elaborate", "illustrate", "clarify",
        "define", "state", "name", "list", "identify", "distinguish", "differentiate",
        "compare", "prove", "derive", "show", "verify", "solve", "select", "choose",
    }

    # Negative heading / section indicators
    HEADING_PATTERNS = [
        re.compile(r"^(?:section|part|unit|module|chapter|paper)\s+[A-Z0-9]+", re.IGNORECASE),
        re.compile(r"^(?:instructions?|notes?|general instructions?|time allowed|maximum marks|total marks)", re.IGNORECASE),
        re.compile(r"^(?:introduction|references|contents|table of contents|appendix|bibliography|acknowledgements?)", re.IGNORECASE),
        re.compile(r"^page\s+[0-9]+\s+(?:of|\/)\s+[0-9]+", re.IGNORECASE),
        re.compile(r"^(?:all questions are compulsory|answer any [0-9]+ questions?)", re.IGNORECASE),
    ]

    def is_heading(self, text: str) -> bool:
        """Check if line matches typical exam headers, sections, or instructions."""
        cleaned = text.strip()
        for pattern in self.HEADING_PATTERNS:
            if pattern.search(cleaned):
                return True
        return False

    def evaluate_line(
        self,
        line: str,
        line_idx: int,
        next_line: Optional[str] = None,
    ) -> Optional[DetectedBoundary]:
        """Evaluate whether a line represents the start of a question and return boundary details."""
        trimmed = line.strip()
        if not trimmed or len(trimmed) < 3:
            return None

        # 1. Negative filter: obvious headings / instructions
        if self.is_heading(trimmed):
            return None

        score = 0.0
        q_num: Optional[str] = None
        remaining_text = trimmed

        # 2. Check explicit prefix: Q1., Question 1:
        match_prefix = self.QUESTION_PREFIX_PATTERN.match(trimmed)
        if match_prefix:
            q_num = match_prefix.group(1)
            remaining_text = match_prefix.group(2).strip()
            score += 0.6

        # 3. Check standard numeric numbering: 1., 1), 12.
        if not q_num:
            match_num = self.NUMERIC_PATTERN.match(trimmed)
            if match_num:
                candidate_num = match_num.group(1)
                after_num = match_num.group(2).strip()

                # Filter false positives like "1. Introduction" or "2. References"
                if not self.is_heading(after_num):
                    q_num = candidate_num
                    remaining_text = after_num
                    score += 0.5

        # 4. Check parenthesized numeric: (1)
        if not q_num:
            match_paren = self.PAREN_NUMERIC_PATTERN.match(trimmed)
            if match_paren:
                q_num = match_paren.group(1)
                remaining_text = match_paren.group(2).strip()
                score += 0.25

        # 5. Check Roman numerals: I., II., (I)
        if not q_num:
            match_roman = self.ROMAN_PATTERN.match(trimmed)
            if match_roman:
                is_standard_roman = match_roman.group(1) is not None
                q_num = (match_roman.group(1) or match_roman.group(2)).upper()
                remaining_text = match_roman.group(3).strip()
                score += 0.4 if is_standard_roman else 0.25

        # 6. Linguistic signals in the remaining text
        words = remaining_text.split()
        first_word = words[0].lower().strip(".,:;()") if words else ""

        if first_word in self.QUESTION_START_WORDS:
            score += 0.3

        if remaining_text.endswith("?") or "?" in remaining_text:
            score += 0.25
        elif remaining_text.endswith(":"):
            score += 0.15

        # 7. Contextual lookahead: does next line look like an option (e.g. A) or (A))?
        if next_line:
            next_trimmed = next_line.strip()
            if re.match(r"^(?:[A-Da-d][\.\)]|\([A-Da-d]\)|Option\s+[A-D])", next_trimmed):
                score += 0.25

        # 8. Unnumbered question detection (e.g. "Which of the following is correct?")
        if not q_num:
            if (
                first_word in self.QUESTION_START_WORDS
                and len(words) >= 4
                and (remaining_text.endswith("?") or (next_line and re.match(r"^(?:[A-Da-d][\.\)]|\([A-Da-d]\))", next_line.strip())))
            ):
                score += 0.45  # Qualifies as an unnumbered question

        # Threshold decision
        if score >= 0.4:
            return DetectedBoundary(
                line_index=line_idx,
                question_number=q_num,
                score=score,
                raw_line=line,
                remaining_text=remaining_text,
            )

        return None


question_boundary_detector = QuestionBoundaryDetector()
