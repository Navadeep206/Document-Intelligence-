"""Validation and sanitization rules for extracted questions and options."""

import re
from typing import Optional

from app.db.models.enums import QuestionStatus
from app.services.extraction.models import ExtractedOption, ExtractedQuestion


class ExtractionValidator:
    """Validates and sanitizes intermediate ExtractedQuestion objects before persistence."""

    MIN_STEM_LENGTH = 3

    def validate(self, question: ExtractedQuestion) -> ExtractedQuestion:
        """Validate question properties, sanitizing values and setting QuestionStatus."""
        notes: list[str] = []
        is_valid = True

        # 1. Validate question stem text
        cleaned_stem = question.question_text.strip()
        # Remove repeated whitespace
        cleaned_stem = re.sub(r"[ \t]+", " ", cleaned_stem)
        question.question_text = cleaned_stem

        if len(cleaned_stem) < self.MIN_STEM_LENGTH:
            notes.append(f"Question stem text is too short ({len(cleaned_stem)} chars).")
            is_valid = False

        # 2. Validate source pages
        if not question.source_pages:
            notes.append("No source pages linked to question.")
            is_valid = False

        # 3. Validate and sanitize options
        sanitized_options: list[ExtractedOption] = []
        seen_labels: set[str] = set()

        for idx, opt in enumerate(question.options, start=1):
            clean_label = opt.label.strip().upper()
            clean_opt_text = opt.text.strip()

            if clean_label in seen_labels:
                notes.append(f"Duplicate option label '{clean_label}' detected at position {idx}.")
                # Generate unique label fallback
                clean_label = f"{clean_label}_{idx}"

            seen_labels.add(clean_label)

            if not clean_opt_text:
                notes.append(f"Option '{clean_label}' text is empty.")

            sanitized_options.append(
                ExtractedOption(
                    label=clean_label,
                    text=clean_opt_text,
                    position=idx,  # Guarantee sequential 1-indexing
                )
            )

        question.options = sanitized_options

        # 4. Set validation notes and status
        question.validation_notes = notes
        question.is_valid = is_valid

        if not is_valid:
            question.status = QuestionStatus.PARTIAL
        else:
            question.status = QuestionStatus.EXTRACTED

        return question


extraction_validator = ExtractionValidator()
