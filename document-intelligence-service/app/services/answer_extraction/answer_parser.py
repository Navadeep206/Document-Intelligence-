"""Parser for answer entries across single-line, multi-column, and diverse format styles."""

import re
from typing import Optional

from app.services.answer_extraction.answer_models import ParsedAnswerEntry


class AnswerParser:
    """Parses answer-key lines into structured ParsedAnswerEntry objects."""

    # Multi-entry grid pattern for lines like: "1. A   2. B   3. C   4. D" or "1-A 2-B 3-C"
    GRID_ENTRY_PATTERN = re.compile(
        r"(?:(?<=\s)|(?<=^))(?:Question\s+|Q\.?\s*)?([0-9]{1,4})\s*(?:[\.\)\:\-\–\—\=]|\s+)\s*([A-Da-d0-9\.\,\/\+\-\?]+(?:\s*(?:or|\/|\,)\s*[A-Da-d0-9]+)?)(?=\s+(?:Q\.?\s*)?[0-9]{1,4}|\s*$)",
        re.IGNORECASE,
    )

    # Single-line answer entry: "1. A", "1 - B", "Q1: C", "Question 15: True", "1 A"
    SINGLE_ENTRY_PATTERN = re.compile(
        r"^(?:Question\s+(?:No\.?\s*)?|Q\.?\s*)?([0-9]{1,4}|[IVXLCDM]+)\s*(?:[\.\)\:\-\–\—\=]|\s+)\s*(.*)$",
        re.IGNORECASE,
    )

    # Patterns indicating an uncertain or unidentifiable answer
    UNCERTAIN_PATTERNS = [
        re.compile(r"^(?:\?+|unclear|unknown|n\/?a|\-+|\*+)$", re.IGNORECASE),
    ]

    def normalize_reference(self, raw_ref: str) -> str:
        """Normalize raw question reference (e.g., 'Q.15', 'Question 15', '01') into canonical number."""
        cleaned = raw_ref.strip()
        # Strip prefix words
        prefix_match = re.match(r"^(?:Question\s+(?:No\.?\s*)?|Q\.?\s*)(.*)$", cleaned, re.IGNORECASE)
        if prefix_match:
            cleaned = prefix_match.group(1).strip()

        # Strip trailing punctuation
        cleaned = re.sub(r"[\.\)\:\-\–\—]$", "", cleaned).strip()

        # Remove leading zeroes if numeric (e.g. '01' -> '1')
        if cleaned.isdigit() and len(cleaned) > 1:
            cleaned = str(int(cleaned))

        return cleaned

    def parse_line(self, line: str, page_number: Optional[int] = None) -> list[ParsedAnswerEntry]:
        """Parse a single text line into one or more ParsedAnswerEntry objects."""
        trimmed = line.strip()
        if not trimmed:
            return []

        # 1. Attempt grid detection first (e.g., "1. A  2. B  3. C  4. D")
        grid_matches = list(self.GRID_ENTRY_PATTERN.finditer(trimmed))
        if len(grid_matches) >= 2:
            entries: list[ParsedAnswerEntry] = []
            for match in grid_matches:
                raw_ref = match.group(1).strip()
                ans_val = match.group(2).strip()
                norm_ref = self.normalize_reference(raw_ref)
                is_uncert = self._is_uncertain_answer(ans_val)

                entries.append(
                    ParsedAnswerEntry(
                        question_reference=raw_ref,
                        normalized_reference=norm_ref,
                        answer_value=ans_val,
                        source_page=page_number,
                        confidence=0.0 if is_uncert else 1.0,
                        is_uncertain=is_uncert,
                        raw_text=match.group(0).strip(),
                    )
                )
            return entries

        # 2. Match single answer entry on the line
        match_single = self.SINGLE_ENTRY_PATTERN.match(trimmed)
        if match_single:
            raw_ref = match_single.group(1).strip()
            ans_val = match_single.group(2).strip()

            if not ans_val:
                return []

            norm_ref = self.normalize_reference(raw_ref)
            is_uncert = self._is_uncertain_answer(ans_val)

            return [
                ParsedAnswerEntry(
                    question_reference=raw_ref,
                    normalized_reference=norm_ref,
                    answer_value=ans_val,
                    source_page=page_number,
                    confidence=0.0 if is_uncert else 1.0,
                    is_uncertain=is_uncert,
                    raw_text=trimmed,
                )
            ]

        return []

    def _is_uncertain_answer(self, value: str) -> bool:
        """Check if extracted answer value represents an uncertain, missing, or unclear entry."""
        val_clean = value.strip().lower()
        for pattern in self.UNCERTAIN_PATTERNS:
            if pattern.match(val_clean):
                return True
        return False


answer_parser = AnswerParser()
