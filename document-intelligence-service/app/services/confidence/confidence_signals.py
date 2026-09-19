"""Measurable signal evaluators for the Confidence Engine."""

import re
from typing import Optional, Sequence
import uuid

from app.db.models.answer import AnswerMapping
from app.db.models.enums import QuestionType, ReviewSeverity
from app.db.models.page import DocumentPage
from app.db.models.question import Question
from app.services.confidence.models import ReviewItemSpec, ReviewReasonCode


class SignalEvaluator:
    """Evaluates discrete, measurable engineering signals on Question domain models."""

    # Patterns for garbage or OCR-distorted characters
    CORRUPTED_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]")
    SUSPICIOUS_TOKEN_PATTERN = re.compile(r"[~|\\^_{}]{2,}")

    def evaluate_ocr_quality(
        self,
        question: Question,
        pages_by_id: dict[uuid.UUID, DocumentPage],
    ) -> tuple[float, list[ReviewItemSpec]]:
        """Evaluate OCR clarity and text sanity across contributing pages."""
        review_items: list[ReviewItemSpec] = []
        if not question.sources:
            return 0.0, [
                ReviewItemSpec(
                    reason=ReviewReasonCode.MISSING_SOURCE_REFERENCE.value,
                    severity=ReviewSeverity.CRITICAL,
                    details="Question has no source page records linked to it",
                    confidence=0.0,
                    question_id=question.id,
                )
            ]

        ocr_scores: list[float] = []
        primary_page_id: Optional[uuid.UUID] = None

        for source in question.sources:
            if primary_page_id is None:
                primary_page_id = source.document_page_id
            page = pages_by_id.get(source.document_page_id)
            if not page:
                continue

            if not page.ocr_used:
                # Native digital text extraction: inherently clean
                ocr_scores.append(1.0)
            else:
                # Tesseract OCR confidence
                conf = page.ocr_confidence if page.ocr_confidence is not None else 0.70
                ocr_scores.append(conf)

        avg_ocr = sum(ocr_scores) / len(ocr_scores) if ocr_scores else 0.50

        # Check for textual corruption / garbage chars
        text = question.question_text or ""
        corrupt_chars = len(self.CORRUPTED_CHAR_PATTERN.findall(text))
        suspicious_tokens = len(self.SUSPICIOUS_TOKEN_PATTERN.findall(text))

        corruption_penalty = 0.0
        if corrupt_chars > 0 or suspicious_tokens > 0:
            corruption_penalty = min(0.40, (corrupt_chars * 0.05) + (suspicious_tokens * 0.10))
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.CORRUPTED_TEXT.value,
                    severity=ReviewSeverity.HIGH,
                    details=f"Question text exhibits distorted characters (corrupt_chars={corrupt_chars}, suspicious={suspicious_tokens})",
                    confidence=max(0.0, avg_ocr - corruption_penalty),
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )

        final_ocr = max(0.0, min(1.0, avg_ocr - corruption_penalty))

        if avg_ocr < 0.65 and not corruption_penalty:
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.LOW_OCR_CONFIDENCE.value,
                    severity=ReviewSeverity.MEDIUM,
                    details=f"Average OCR confidence across source pages is low ({avg_ocr:.2f})",
                    confidence=final_ocr,
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )

        return final_ocr, review_items

    def evaluate_question_text_quality(
        self,
        question: Question,
    ) -> tuple[float, list[ReviewItemSpec]]:
        """Evaluate completeness, length, and syntactic cohesion of question stem."""
        review_items: list[ReviewItemSpec] = []
        text = (question.question_text or "").strip()

        primary_page_id = question.sources[0].document_page_id if question.sources else None

        if not text or len(text) < 10:
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.INCOMPLETE_QUESTION.value,
                    severity=ReviewSeverity.HIGH,
                    details=f"Question text is extremely brief or empty ({len(text)} characters)",
                    confidence=0.20,
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )
            return 0.20, review_items

        # Check for abrupt truncation (ends in dangling hyphen or ellipsis)
        if text.endswith(("-", "...", "…", "/")):
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.INCOMPLETE_QUESTION.value,
                    severity=ReviewSeverity.HIGH,
                    details="Question stem ends abruptly with truncation markers",
                    confidence=0.50,
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )
            return 0.50, review_items

        # Check for textual corruption / distortion in stem
        corrupt_chars = len(self.CORRUPTED_CHAR_PATTERN.findall(text))
        suspicious_tokens = len(self.SUSPICIOUS_TOKEN_PATTERN.findall(text))
        corruption_penalty = 0.0
        if corrupt_chars > 0 or suspicious_tokens > 0:
            corruption_penalty = min(0.50, (corrupt_chars * 0.10) + (suspicious_tokens * 0.15))

        base_score = 0.80 if len(text) < 20 else 1.0
        final_score = max(0.20, base_score - corruption_penalty)
        return final_score, review_items

    def evaluate_boundary_confidence(
        self,
        question: Question,
    ) -> tuple[float, list[ReviewItemSpec]]:
        """Evaluate boundary certainty and separation from adjacent content."""
        review_items: list[ReviewItemSpec] = []
        qnum = question.question_number
        text = question.question_text or ""
        primary_page_id = question.sources[0].document_page_id if question.sources else None

        # Check if multiple questions were accidentally merged (multiple terminal question marks)
        qmark_count = text.count("?")
        if qmark_count >= 2 and len(text) > 200:
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.AMBIGUOUS_QUESTION_BOUNDARY.value,
                    severity=ReviewSeverity.HIGH,
                    details=f"Question stem contains {qmark_count} question marks, indicating possible merged questions",
                    confidence=0.45,
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )
            return 0.45, review_items

        if qnum:
            return 1.0, review_items

        # Unnumbered questions have lower boundary confidence
        return 0.70, review_items

    def evaluate_question_number_confidence(
        self,
        question: Question,
        duplicate_numbers_in_doc: set[str],
    ) -> tuple[float, list[ReviewItemSpec]]:
        """Evaluate question numbering consistency and uniqueness."""
        review_items: list[ReviewItemSpec] = []
        qnum = question.question_number
        primary_page_id = question.sources[0].document_page_id if question.sources else None

        if not qnum or not qnum.strip():
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.MISSING_QUESTION_NUMBER.value,
                    severity=ReviewSeverity.LOW,
                    details="Question has no detected numbering label",
                    confidence=0.40,
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )
            return 0.40, review_items

        cleaned_num = qnum.strip()
        if cleaned_num in duplicate_numbers_in_doc:
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.AMBIGUOUS_QUESTION_BOUNDARY.value,
                    severity=ReviewSeverity.HIGH,
                    details=f"Question number '{cleaned_num}' appears more than once in this document",
                    confidence=0.35,
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )
            return 0.35, review_items

        return 1.0, review_items

    def evaluate_option_completeness(
        self,
        question: Question,
    ) -> tuple[float, list[ReviewItemSpec]]:
        """Evaluate multiple-choice options completeness without penalizing non-MCQs."""
        review_items: list[ReviewItemSpec] = []
        primary_page_id = question.sources[0].document_page_id if question.sources else None

        # Descriptive, numerical, and short-answer questions are not penalized
        if question.question_type in (
            QuestionType.SHORT_ANSWER,
            QuestionType.LONG_ANSWER,
            QuestionType.NUMERICAL,
        ):
            return 1.0, review_items

        if question.question_type == QuestionType.TRUE_FALSE:
            if not question.options or len(question.options) == 0:
                # Phrased in stem: acceptable
                return 0.90, review_items
            if len(question.options) >= 2:
                return 1.0, review_items
            return 0.70, review_items

        if question.question_type == QuestionType.MCQ:
            options = question.options or []
            if len(options) == 0:
                review_items.append(
                    ReviewItemSpec(
                        reason=ReviewReasonCode.INCOMPLETE_OPTIONS.value,
                        severity=ReviewSeverity.MEDIUM,
                        details="MCQ question classified without any extracted options",
                        confidence=0.25,
                        question_id=question.id,
                        page_id=primary_page_id,
                    )
                )
                return 0.25, review_items

            if len(options) == 1:
                review_items.append(
                    ReviewItemSpec(
                        reason=ReviewReasonCode.INCOMPLETE_OPTIONS.value,
                        severity=ReviewSeverity.MEDIUM,
                        details="Only 1 choice was extracted for this multiple-choice question",
                        confidence=0.45,
                        question_id=question.id,
                        page_id=primary_page_id,
                    )
                )
                return 0.45, review_items

            # Check sequence continuity for lettered options (e.g. A, B, D missing C)
            labels = [opt.label.upper().strip() for opt in options if opt.label]
            is_letter_sequence = all(len(l) == 1 and "A" <= l <= "Z" for l in labels)

            if is_letter_sequence and len(labels) >= 2:
                ord_values = [ord(l) for l in labels]
                min_val = min(ord_values)
                max_val = max(ord_values)
                expected_count = max_val - min_val + 1
                if expected_count != len(labels):
                    missing_labels = [chr(c) for c in range(min_val, max_val + 1) if c not in ord_values]
                    review_items.append(
                        ReviewItemSpec(
                            reason=ReviewReasonCode.MISSING_OPTION.value,
                            severity=ReviewSeverity.MEDIUM,
                            details=f"Options sequence has gaps: missing {missing_labels} (found {labels})",
                            confidence=0.60,
                            question_id=question.id,
                            page_id=primary_page_id,
                        )
                    )
                    return 0.60, review_items

            # Check for empty option text
            has_empty_option = any(not (opt.option_text or "").strip() for opt in options)
            if has_empty_option:
                review_items.append(
                    ReviewItemSpec(
                        reason=ReviewReasonCode.INCOMPLETE_OPTIONS.value,
                        severity=ReviewSeverity.MEDIUM,
                        details="One or more multiple-choice options have empty text",
                        confidence=0.65,
                        question_id=question.id,
                        page_id=primary_page_id,
                    )
                )
                return 0.65, review_items

            return 1.0, review_items

        # Fallback for UNKNOWN
        return 0.85, review_items

    def evaluate_source_traceability(
        self,
        question: Question,
    ) -> tuple[float, list[ReviewItemSpec]]:
        """Verify linking to physical document page records."""
        review_items: list[ReviewItemSpec] = []
        if not question.sources:
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.MISSING_SOURCE_REFERENCE.value,
                    severity=ReviewSeverity.CRITICAL,
                    details="Question has no source page traceability records",
                    confidence=0.0,
                    question_id=question.id,
                )
            )
            return 0.0, review_items

        return 1.0, review_items

    def evaluate_page_continuity(
        self,
        question: Question,
        pages_by_id: dict[uuid.UUID, DocumentPage],
    ) -> tuple[float, list[ReviewItemSpec]]:
        """Verify sequential continuity for multi-page questions."""
        review_items: list[ReviewItemSpec] = []
        sources = question.sources or []
        if len(sources) <= 1:
            return 1.0, review_items

        # Retrieve page numbers in order of sequence
        page_numbers: list[int] = []
        for s in sorted(sources, key=lambda x: x.page_sequence):
            page = pages_by_id.get(s.document_page_id)
            if page:
                page_numbers.append(page.page_number)

        if len(page_numbers) > 1:
            for i in range(len(page_numbers) - 1):
                if page_numbers[i + 1] - page_numbers[i] > 1:
                    # Non-consecutive gap detected
                    review_items.append(
                        ReviewItemSpec(
                            reason=ReviewReasonCode.MULTI_PAGE_UNCERTAINTY.value,
                            severity=ReviewSeverity.HIGH,
                            details=f"Question spans non-consecutive pages: {page_numbers}",
                            confidence=0.40,
                            question_id=question.id,
                            page_id=sources[0].document_page_id,
                        )
                    )
                    return 0.40, review_items

        # Multi-page with strong continuity is valid and not penalized
        return 1.0, review_items

    def evaluate_answer_mapping(
        self,
        question: Question,
        document_has_answer_key: bool,
        ambiguous_qrefs: set[str],
    ) -> tuple[float, list[ReviewItemSpec]]:
        """Evaluate answer mapping state without penalizing documents lacking answer keys."""
        review_items: list[ReviewItemSpec] = []
        primary_page_id = question.sources[0].document_page_id if question.sources else None
        qnum = (question.question_number or "").strip()

        if not document_has_answer_key:
            # Neutral baseline: no answer key was uploaded for this document
            return 0.85, review_items

        if question.answer is not None:
            ans_conf = question.answer_confidence if question.answer_confidence is not None else 0.95
            if ans_conf >= 0.85:
                # High-confidence exact match
                return 1.0, review_items
            else:
                review_items.append(
                    ReviewItemSpec(
                        reason=ReviewReasonCode.AMBIGUOUS_ANSWER.value,
                        severity=ReviewSeverity.HIGH,
                        details=f"Associated answer '{question.answer}' has low/ambiguous confidence ({ans_conf:.2f})",
                        confidence=ans_conf,
                        question_id=question.id,
                        page_id=primary_page_id,
                    )
                )
                return ans_conf, review_items

        # Answer is None despite document possessing an answer key
        if qnum and qnum in ambiguous_qrefs:
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.AMBIGUOUS_ANSWER.value,
                    severity=ReviewSeverity.HIGH,
                    details=f"Multiple ambiguous answer mappings exist for question reference '{qnum}'",
                    confidence=0.30,
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )
            return 0.30, review_items

        # Unmatched answer
        review_items.append(
            ReviewItemSpec(
                reason=ReviewReasonCode.UNMATCHED_ANSWER.value,
                severity=ReviewSeverity.MEDIUM,
                details=f"No answer key entry was associated with question '{qnum or 'un-numbered'}'",
                confidence=0.50,
                question_id=question.id,
                page_id=primary_page_id,
            )
        )
        return 0.50, review_items


signal_evaluator = SignalEvaluator()
