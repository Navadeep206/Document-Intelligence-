"""Validation and sanitization rules for answer entries and mappings."""

from typing import Optional
import uuid

from app.services.answer_extraction.answer_models import MatchResult, ParsedAnswerEntry


class AnswerValidator:
    """Validates answer-key entries and association results before database persistence."""

    def validate_entry(self, entry: ParsedAnswerEntry) -> bool:
        """Verify individual entry constraints (non-empty reference, non-empty answer, positive page)."""
        if not entry.question_reference or not entry.question_reference.strip():
            return False

        if not entry.answer_value or not entry.answer_value.strip():
            return False

        if entry.source_page is not None and entry.source_page <= 0:
            return False

        if entry.confidence < 0.0 or entry.confidence > 1.0:
            return False

        return True

    def validate_match(
        self,
        match: MatchResult,
        expected_question_document_id: uuid.UUID,
        valid_question_ids: set[uuid.UUID],
    ) -> MatchResult:
        """Ensure matched question belongs exclusively to the target question document."""
        if match.matched_question_id is not None:
            if match.matched_question_id not in valid_question_ids:
                match.notes.append(
                    f"Rejected cross-document question link: {match.matched_question_id} not in target document."
                )
                match.matched_question_id = None
                match.confidence = 0.0
                match.match_strategy = "INVALID_DOCUMENT"

        # Clamp confidence to valid database range [0.0, 1.0]
        match.confidence = max(0.0, min(1.0, match.confidence))
        return match


answer_validator = AnswerValidator()
