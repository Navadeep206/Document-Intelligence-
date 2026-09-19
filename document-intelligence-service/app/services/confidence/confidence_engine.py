"""Weighted confidence calculation and status classification engine."""

import logging
from typing import Optional, Sequence
import uuid

from app.core.config import Settings, get_settings
from app.db.models.enums import QuestionStatus, ReviewSeverity
from app.db.models.page import DocumentPage
from app.db.models.question import Question
from app.services.confidence.confidence_signals import signal_evaluator
from app.services.confidence.models import (
    ConfidenceResult,
    ConfidenceSignals,
    ReviewItemSpec,
    ReviewReasonCode,
)

logger = logging.getLogger("document-intelligence-service")


class ConfidenceEngine:
    """Orchestrates deterministic, explainable confidence evaluation across measurable signals."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def evaluate_question(
        self,
        question: Question,
        pages_by_id: dict[uuid.UUID, DocumentPage],
        duplicate_numbers_in_doc: set[str],
        document_has_answer_key: bool = False,
        ambiguous_qrefs: Optional[set[str]] = None,
    ) -> ConfidenceResult:
        """Calculate weighted confidence, explainable signals, and candidate review items."""
        ambiguous_refs = ambiguous_qrefs or set()
        review_items: list[ReviewItemSpec] = []

        # 1. Evaluate discrete signals
        ocr_score, ocr_reviews = signal_evaluator.evaluate_ocr_quality(question, pages_by_id)
        review_items.extend(ocr_reviews)

        text_score, text_reviews = signal_evaluator.evaluate_question_text_quality(question)
        review_items.extend(text_reviews)

        boundary_score, boundary_reviews = signal_evaluator.evaluate_boundary_confidence(question)
        review_items.extend(boundary_reviews)

        number_score, number_reviews = signal_evaluator.evaluate_question_number_confidence(
            question, duplicate_numbers_in_doc
        )
        review_items.extend(number_reviews)

        options_score, options_reviews = signal_evaluator.evaluate_option_completeness(question)
        review_items.extend(options_reviews)

        source_score, source_reviews = signal_evaluator.evaluate_source_traceability(question)
        review_items.extend(source_reviews)

        page_score, page_reviews = signal_evaluator.evaluate_page_continuity(question, pages_by_id)
        review_items.extend(page_reviews)

        answer_score, answer_reviews = signal_evaluator.evaluate_answer_mapping(
            question, document_has_answer_key, ambiguous_refs
        )
        review_items.extend(answer_reviews)

        # 2. Compute weighted score
        w = self.settings
        overall = (
            (ocr_score * w.CONFIDENCE_OCR_WEIGHT)
            + (text_score * w.CONFIDENCE_TEXT_WEIGHT)
            + (boundary_score * w.CONFIDENCE_BOUNDARY_WEIGHT)
            + (number_score * w.CONFIDENCE_NUMBER_WEIGHT)
            + (options_score * w.CONFIDENCE_OPTIONS_WEIGHT)
            + (source_score * w.CONFIDENCE_SOURCE_WEIGHT)
            + (page_score * w.CONFIDENCE_PAGE_WEIGHT)
            + (answer_score * w.CONFIDENCE_ANSWER_WEIGHT)
        )
        overall = max(0.0, min(1.0, overall))

        signals = ConfidenceSignals(
            ocr_quality=ocr_score,
            question_text_quality=text_score,
            boundary_confidence=boundary_score,
            question_number_confidence=number_score,
            option_completeness=options_score,
            source_traceability=source_score,
            page_continuity=page_score,
            answer_mapping=answer_score,
        )

        field_confidence = {
            "question_text": text_score,
            "question_number": number_score,
            "options": options_score,
            "answer": answer_score,
            "ocr": ocr_score,
        }

        # 3. Add overall confidence review item if below threshold
        primary_page_id = question.sources[0].document_page_id if question.sources else None
        if overall < 0.40:
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.LOW_OVERALL_CONFIDENCE.value,
                    severity=ReviewSeverity.CRITICAL,
                    details=f"Overall question confidence is critically low ({overall:.2f})",
                    confidence=overall,
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )
        elif overall < w.CONFIDENCE_THRESHOLD_PARTIAL:
            review_items.append(
                ReviewItemSpec(
                    reason=ReviewReasonCode.LOW_OVERALL_CONFIDENCE.value,
                    severity=ReviewSeverity.HIGH,
                    details=f"Overall question confidence ({overall:.2f}) is below minimum threshold ({w.CONFIDENCE_THRESHOLD_PARTIAL})",
                    confidence=overall,
                    question_id=question.id,
                    page_id=primary_page_id,
                )
            )

        # 4. Determine status classification and review requirement
        has_high_or_critical = any(
            item.severity in (ReviewSeverity.HIGH, ReviewSeverity.CRITICAL)
            for item in review_items
        )

        if overall >= w.CONFIDENCE_THRESHOLD_EXTRACTED:
            if has_high_or_critical:
                status = QuestionStatus.REVIEW_REQUIRED
                review_required = True
            elif review_items:
                # Minor warnings (e.g. LOW severity missing number) keep status EXTRACTED but mark review
                status = QuestionStatus.EXTRACTED
                review_required = True
            else:
                status = QuestionStatus.EXTRACTED
                review_required = False
        elif overall >= w.CONFIDENCE_THRESHOLD_PARTIAL:
            status = QuestionStatus.PARTIAL
            review_required = True
        else:
            status = QuestionStatus.REVIEW_REQUIRED
            review_required = True

        # Extract unique reason codes
        reason_codes: list[ReviewReasonCode] = []
        for item in review_items:
            try:
                code = ReviewReasonCode(item.reason)
                if code not in reason_codes:
                    reason_codes.append(code)
            except ValueError:
                pass

        logger.debug(
            "Question %s evaluated: overall=%.3f, status=%s, review_required=%s, reasons=%s",
            question.id,
            overall,
            status.value,
            review_required,
            [r.value for r in reason_codes],
        )

        return ConfidenceResult(
            overall_confidence=overall,
            status=status,
            signals=signals,
            review_required=review_required,
            reasons=reason_codes,
            review_items=review_items,
            field_confidence=field_confidence,
        )


confidence_engine = ConfidenceEngine()
