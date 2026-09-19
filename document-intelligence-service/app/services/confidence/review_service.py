"""ReviewItem lifecycle management, deduplication, and document summary service."""

import datetime
import logging
from typing import Optional, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.answer import AnswerKey, AnswerMapping
from app.db.models.document import Document
from app.db.models.enums import QuestionStatus, ReviewSeverity, ReviewStatus
from app.db.models.page import DocumentPage
from app.db.models.question import Question
from app.db.models.review import ReviewItem
from app.services.confidence.confidence_engine import confidence_engine
from app.services.confidence.models import (
    ConfidenceResult,
    DocumentReviewSummary,
    ReviewItemSpec,
    ReviewReasonCode,
)

logger = logging.getLogger("document-intelligence-service")


class ReviewService:
    """Manages creation, deduplication, resolution, and telemetry for ReviewItem entities."""

    def sync_document_reviews(
        self,
        document_id: uuid.UUID,
        db: Session,
    ) -> DocumentReviewSummary:
        """Evaluate confidence for all questions in document and idempotently sync review items."""
        # 1. Fetch document and related pages
        doc = db.scalar(select(Document).where(Document.id == document_id))
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        pages = db.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        ).all()
        pages_by_id = {p.id: p for p in pages}

        # 2. Fetch questions with sources and options eagerly loaded
        questions = db.scalars(
            select(Question)
            .where(Question.document_id == document_id)
            .options(
                selectinload(Question.options),
                selectinload(Question.sources),
                selectinload(Question.answer_mappings),
            )
            .order_by(Question.created_at)
        ).all()

        # 3. Detect duplicate question numbers in document
        qnum_counts: dict[str, int] = {}
        for q in questions:
            if q.question_number and q.question_number.strip():
                num = q.question_number.strip()
                qnum_counts[num] = qnum_counts.get(num, 0) + 1
        duplicate_numbers = {num for num, count in qnum_counts.items() if count > 1}

        # 4. Check answer keys and ambiguous answer references
        has_answer_key = (
            db.scalar(
                select(func.count(AnswerKey.id)).where(AnswerKey.document_id == document_id)
            )
            > 0
        )

        ambiguous_qrefs: set[str] = set()
        if has_answer_key:
            mappings = db.scalars(
                select(AnswerMapping).join(AnswerKey).where(AnswerKey.document_id == document_id)
            ).all()
            for m in mappings:
                if m.question_id is None:
                    ambiguous_qrefs.add(m.question_reference)

        # 5. Evaluate confidence for each question and gather review specs
        all_review_specs: list[ReviewItemSpec] = []
        for q in questions:
            eval_result: ConfidenceResult = confidence_engine.evaluate_question(
                question=q,
                pages_by_id=pages_by_id,
                duplicate_numbers_in_doc=duplicate_numbers,
                document_has_answer_key=has_answer_key,
                ambiguous_qrefs=ambiguous_qrefs,
            )
            q.confidence = eval_result.overall_confidence
            q.status = eval_result.status
            all_review_specs.extend(eval_result.review_items)

        # 6. Idempotent sync of review items
        existing_items = db.scalars(
            select(ReviewItem).where(ReviewItem.document_id == document_id)
        ).all()
        existing_by_key: dict[tuple[Optional[uuid.UUID], str], ReviewItem] = {
            (item.question_id, item.reason): item for item in existing_items
        }

        fresh_keys: set[tuple[Optional[uuid.UUID], str]] = set()

        for spec in all_review_specs:
            key = (spec.question_id, spec.reason)
            fresh_keys.add(key)

            if key in existing_by_key:
                existing = existing_by_key[key]
                if existing.status == ReviewStatus.OPEN:
                    # Update details and confidence on open items
                    existing.details = spec.details
                    existing.confidence = spec.confidence
                    existing.severity = spec.severity
                    logger.debug("Updated existing OPEN review item %s (%s)", existing.id, spec.reason)
                else:
                    # User previously RESOLVED or IGNORED this item: respect resolution
                    existing.details = spec.details
                    existing.confidence = spec.confidence
                    logger.debug("Preserved user resolution for review item %s (%s)", existing.id, existing.status.value)
            else:
                # Insert fresh ReviewItem
                new_item = ReviewItem(
                    document_id=document_id,
                    question_id=spec.question_id,
                    page_id=spec.page_id,
                    severity=spec.severity,
                    status=ReviewStatus.OPEN,
                    reason=spec.reason,
                    details=spec.details,
                    confidence=spec.confidence,
                )
                db.add(new_item)
                logger.info("Created fresh review item for doc %s, q %s: %s", document_id, spec.question_id, spec.reason)

        # 7. Prune stale OPEN items that are no longer present in fresh evaluation
        for key, existing in existing_by_key.items():
            if key not in fresh_keys and existing.status == ReviewStatus.OPEN:
                logger.info("Pruning stale OPEN review item %s (%s) for document %s", existing.id, existing.reason, document_id)
                db.delete(existing)

        db.commit()

        return self.get_document_summary(document_id, db)

    def get_document_summary(
        self,
        document_id: uuid.UUID,
        db: Session,
    ) -> DocumentReviewSummary:
        """Compute aggregate review and confidence metrics for a document."""
        questions = db.scalars(
            select(Question).where(Question.document_id == document_id)
        ).all()

        total_questions = len(questions)
        high_conf = sum(1 for q in questions if (q.confidence or 0.0) >= 0.85 and q.status == QuestionStatus.EXTRACTED)
        partial = sum(1 for q in questions if q.status == QuestionStatus.PARTIAL)
        review_req = sum(1 for q in questions if q.status == QuestionStatus.REVIEW_REQUIRED or (q.confidence or 0.0) < 0.60)

        review_items = db.scalars(
            select(ReviewItem).where(ReviewItem.document_id == document_id)
        ).all()

        open_count = sum(1 for item in review_items if item.status == ReviewStatus.OPEN)
        resolved_count = sum(1 for item in review_items if item.status == ReviewStatus.RESOLVED)
        ignored_count = sum(1 for item in review_items if item.status == ReviewStatus.IGNORED)

        # Count answer issues from review items
        unmatched_ans = sum(1 for item in review_items if item.reason == ReviewReasonCode.UNMATCHED_ANSWER.value)
        ambiguous_ans = sum(1 for item in review_items if item.reason == ReviewReasonCode.AMBIGUOUS_ANSWER.value)

        return DocumentReviewSummary(
            document_id=document_id,
            total_questions=total_questions,
            high_confidence_questions=high_conf,
            partial_questions=partial,
            review_required_questions=review_req,
            open_review_items=open_count,
            resolved_review_items=resolved_count,
            ignored_review_items=ignored_count,
            unmatched_answers=unmatched_ans,
            ambiguous_answers=ambiguous_ans,
        )

    def resolve_review_item(
        self,
        review_id: uuid.UUID,
        new_status: ReviewStatus,
        current_user_id: uuid.UUID,
        db: Session,
    ) -> ReviewItem:
        """Update review item status with ownership validation."""
        item = db.scalar(
            select(ReviewItem)
            .join(Document, ReviewItem.document_id == Document.id)
            .where(ReviewItem.id == review_id, Document.owner_id == current_user_id)
        )
        if not item:
            raise ValueError(f"Review item {review_id} not found or not owned by user")

        item.status = new_status
        if new_status in (ReviewStatus.RESOLVED, ReviewStatus.IGNORED):
            item.resolved_at = datetime.datetime.now(datetime.timezone.utc)
        else:
            item.resolved_at = None

        db.commit()
        db.refresh(item)
        logger.info("Review item %s status updated to %s by user %s", review_id, new_status.value, current_user_id)
        return item


review_service = ReviewService()
