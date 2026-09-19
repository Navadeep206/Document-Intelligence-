"""Orchestrator for answer-key detection, entry parsing, question matching, and persistence."""

import logging
from typing import Optional, Sequence
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.answer import AnswerKey, AnswerMapping
from app.db.models.document import Document
from app.db.models.enums import AnswerSource, DocumentRole
from app.db.models.page import DocumentPage
from app.db.models.question import Question
from app.services.answer_extraction.answer_key_detector import (
    AnswerKeyDetector,
    answer_key_detector,
)
from app.services.answer_extraction.answer_matcher import AnswerMatcher, answer_matcher
from app.services.answer_extraction.answer_models import (
    AnswerExtractionResult,
    AnswerSection,
    MatchResult,
    ParsedAnswerEntry,
)
from app.services.answer_extraction.answer_parser import AnswerParser, answer_parser
from app.services.answer_extraction.validators import AnswerValidator, answer_validator

logger = logging.getLogger("document-intelligence-service")


class AnswerExtractor:
    """End-to-end service for answer-key detection, extraction, question matching, and persistence."""

    def __init__(
        self,
        detector: Optional[AnswerKeyDetector] = None,
        parser: Optional[AnswerParser] = None,
        matcher: Optional[AnswerMatcher] = None,
        validator: Optional[AnswerValidator] = None,
    ):
        self.detector = detector or answer_key_detector
        self.parser = parser or answer_parser
        self.matcher = matcher or answer_matcher
        self.validator = validator or answer_validator

    def extract_and_associate(
        self,
        question_document_id: uuid.UUID,
        source_document_id: uuid.UUID,
        db: Session,
    ) -> AnswerExtractionResult:
        """Extract answer entries from source document and deterministically link to question document."""
        # 1. Fetch source document and pages
        source_doc = db.scalar(select(Document).where(Document.id == source_document_id))
        if not source_doc:
            logger.error("Source document %s not found for answer extraction.", source_document_id)
            return AnswerExtractionResult(
                document_id=question_document_id,
                source_document_id=source_document_id,
            )

        pages = list(
            db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == source_document_id)
                .order_by(DocumentPage.page_number.asc())
            ).all()
        )

        if not pages:
            logger.warning("No pages found for source document %s during answer extraction.", source_document_id)
            return AnswerExtractionResult(
                document_id=question_document_id,
                source_document_id=source_document_id,
            )

        # 2. Detect answer-key sections
        sections = self.detector.detect_sections(pages, source_doc.document_role)
        if not sections:
            logger.info("No answer-key section detected in source document %s.", source_document_id)
            return AnswerExtractionResult(
                document_id=question_document_id,
                source_document_id=source_document_id,
            )

        # 3. Parse all answer entries from detected sections
        parsed_entries: list[ParsedAnswerEntry] = []
        format_descriptions: list[str] = []

        for sec in sections:
            format_descriptions.append(sec.format_description)
            for page_num, line_text in sec.lines:
                entries = self.parser.parse_line(line_text, page_number=page_num)
                for entry in entries:
                    if self.validator.validate_entry(entry):
                        parsed_entries.append(entry)

        if not parsed_entries:
            logger.info("No valid answer entries parsed from sections in document %s.", source_document_id)
            return AnswerExtractionResult(
                document_id=question_document_id,
                source_document_id=source_document_id,
            )

        # 4. Fetch candidate questions from question document
        candidate_questions = list(
            db.scalars(
                select(Question)
                .where(Question.document_id == question_document_id)
                .order_by(Question.created_at.asc())
            ).all()
        )
        valid_question_ids = {q.id for q in candidate_questions}
        questions_by_id = {q.id: q for q in candidate_questions}

        # 5. Deterministic question matching
        raw_matches = self.matcher.match_answers(parsed_entries, candidate_questions)

        # 6. Validate matches against target document boundaries
        validated_matches: list[MatchResult] = [
            self.validator.validate_match(m, question_document_id, valid_question_ids)
            for m in raw_matches
        ]

        matched_count = sum(1 for m in validated_matches if m.matched_question_id is not None)
        unmatched_count = len(validated_matches) - matched_count

        # Compute aggregate answer-key confidence
        positive_confidences = [m.confidence for m in validated_matches if m.confidence > 0.0]
        overall_conf = (
            sum(positive_confidences) / len(positive_confidences)
            if positive_confidences
            else 0.0
        )

        format_summary = ", ".join(set(format_descriptions)) if format_descriptions else "Standard"

        # 7. Transactional atomic persistence (Idempotent delete-and-rebuild)
        try:
            # Delete existing AnswerKey for this document/source pair (cascades to AnswerMapping)
            existing_key = db.scalar(
                select(AnswerKey).where(
                    AnswerKey.document_id == question_document_id,
                    AnswerKey.source_document_id == source_document_id,
                )
            )
            if existing_key:
                db.delete(existing_key)
                db.flush()

            # Create new AnswerKey
            answer_key = AnswerKey(
                document_id=question_document_id,
                source_document_id=source_document_id,
                name=f"Answer Key for {source_doc.filename}",
                format_description=format_summary,
                confidence=round(overall_conf, 4),
            )
            db.add(answer_key)
            db.flush()

            # Insert mappings and associate answers to Question records
            for match in validated_matches:
                mapping = AnswerMapping(
                    answer_key_id=answer_key.id,
                    question_id=match.matched_question_id,
                    question_reference=match.entry.question_reference,
                    answer_value=match.entry.answer_value,
                    confidence=round(match.confidence, 4),
                    source_page=match.entry.source_page,
                )
                db.add(mapping)

                # If reliably matched to a Question, update question answer fields
                if match.matched_question_id and match.matched_question_id in questions_by_id:
                    q = questions_by_id[match.matched_question_id]
                    q.answer = match.entry.answer_value
                    q.answer_confidence = round(match.confidence, 4)
                    q.answer_source = AnswerSource.ANSWER_KEY

            db.commit()

            # Re-evaluate confidence and sync review items with newly associated answers
            try:
                from app.services.confidence.review_service import review_service
                review_service.sync_document_reviews(question_document_id, db)
            except Exception as rev_err:
                logger.warning("Post-answer review sync failed for %s: %s", question_document_id, rev_err)

            logger.info(
                "Answer extraction completed: doc=%s source=%s total=%d matched=%d unmatched=%d conf=%.2f",
                question_document_id,
                source_document_id,
                len(validated_matches),
                matched_count,
                unmatched_count,
                overall_conf,
            )

            return AnswerExtractionResult(
                document_id=question_document_id,
                source_document_id=source_document_id,
                answer_key_id=answer_key.id,
                total_entries=len(validated_matches),
                matched_count=matched_count,
                unmatched_count=unmatched_count,
                overall_confidence=overall_conf,
                matches=validated_matches,
            )

        except Exception as exc:
            logger.error("Failed to persist answer key for document %s: %s", question_document_id, exc)
            db.rollback()
            raise


answer_extractor = AnswerExtractor()
