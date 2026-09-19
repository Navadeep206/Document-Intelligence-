"""Question extraction orchestrator for structured question extraction and persistence."""

from dataclasses import dataclass
import datetime
import logging
import re
from typing import Optional, Sequence
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.enums import QuestionStatus, QuestionType
from app.db.models.page import DocumentPage
from app.db.models.question import Question, QuestionOption, QuestionSource
from app.services.extraction.models import (
    DocumentExtractionResult,
    ExtractedOption,
    ExtractedQuestion,
)
from app.services.extraction.option_parser import option_parser
from app.services.extraction.question_boundary_detector import question_boundary_detector
from app.services.extraction.question_type_classifier import question_type_classifier
from app.services.extraction.validators import extraction_validator

logger = logging.getLogger("document-intelligence-service")


@dataclass
class _PageLine:
    page_number: int
    page_id: uuid.UUID
    text: str


class QuestionExtractor:
    """Orchestrates question boundary detection, option parsing, classification, and persistence."""

    PAGE_NOISE_PATTERNS = [
        re.compile(
            r"^(?:page\s+[0-9]+(?:\s*(?:of|\/)\s*[0-9]+)?|[0-9]+\s*(?:of|\/)\s*[0-9]+|\-\s*[0-9]+\s*\-)$",
            re.IGNORECASE,
        ),
        re.compile(r"^(?:p\.?t\.?o\.?|please\s+turn\s+over)$", re.IGNORECASE),
    ]

    def _is_page_noise(self, line: str) -> bool:
        """Identify footer/header page number noise lines."""
        cleaned = line.strip()
        for pattern in self.PAGE_NOISE_PATTERNS:
            if pattern.match(cleaned):
                return True
        return False

    def extract_from_text(
        self,
        text: str,
        page_number: int = 1,
        page_id: Optional[uuid.UUID] = None,
    ) -> list[ExtractedQuestion]:
        """Extract questions from raw text content (convenience helper for tests/single-page)."""
        pid = page_id or uuid.uuid4()
        lines = [
            _PageLine(page_number=page_number, page_id=pid, text=line)
            for line in text.splitlines()
            if line.strip() and not self._is_page_noise(line)
        ]
        return self._extract_from_page_lines(lines)

    def extract_questions_from_pages(
        self,
        pages: Sequence[DocumentPage],
    ) -> list[ExtractedQuestion]:
        """Extract structured questions across multiple ordered DocumentPage records."""
        from app.services.answer_extraction.answer_key_detector import answer_key_detector

        # Identify answer-key sections in document to avoid extracting answer entries as questions
        answer_sections = answer_key_detector.detect_sections(pages)
        answer_lines_by_page: set[tuple[int, str]] = set()
        for sec in answer_sections:
            answer_lines_by_page.add((sec.source_page_start, sec.header_text.strip()))
            for p_num, line in sec.lines:
                answer_lines_by_page.add((p_num, line.strip()))

        all_lines: list[_PageLine] = []
        for page in sorted(pages, key=lambda p: p.page_number):
            if not page.text_content:
                continue
            for raw_line in page.text_content.splitlines():
                line = raw_line.strip()
                if not line or self._is_page_noise(line):
                    continue
                if (page.page_number, line) in answer_lines_by_page:
                    continue
                all_lines.append(
                    _PageLine(
                        page_number=page.page_number,
                        page_id=page.id,
                        text=line,
                    )
                )

        return self._extract_from_page_lines(all_lines)

    def _extract_from_page_lines(
        self,
        lines: list[_PageLine],
    ) -> list[ExtractedQuestion]:
        """Process flat sequential line stream with boundary detection and multi-page continuity."""
        questions: list[ExtractedQuestion] = []
        current_qnum: Optional[str] = None
        current_lines: list[str] = []
        current_pages: list[tuple[int, uuid.UUID]] = []

        def flush_current():
            nonlocal current_qnum, current_lines, current_pages
            if not current_lines:
                current_qnum = None
                current_pages = []
                return

            stem, options = option_parser.parse_options(current_lines)
            if not stem:
                stem = " ".join(current_lines)

            q_type = question_type_classifier.classify(stem, options)

            # Deduplicate pages while preserving chronological sequence
            seen_ids: set[uuid.UUID] = set()
            unique_pages: list[tuple[int, uuid.UUID]] = []
            for p_num, p_id in current_pages:
                if p_id not in seen_ids:
                    seen_ids.add(p_id)
                    unique_pages.append((p_num, p_id))

            raw = "\n".join(current_lines)
            eq = ExtractedQuestion(
                question_number=current_qnum,
                question_text=stem,
                question_type=q_type,
                options=options,
                source_pages=unique_pages,
                raw_text=raw,
            )
            validated_eq = extraction_validator.validate(eq)
            questions.append(validated_eq)

            current_qnum = None
            current_lines = []
            current_pages = []

        total_lines = len(lines)
        for i, item in enumerate(lines):
            next_item = lines[i + 1] if i + 1 < total_lines else None
            next_text = next_item.text if next_item else None

            # 1. Negative filter: exam section headers or broad instructions flush current question
            if question_boundary_detector.is_heading(item.text):
                flush_current()
                continue

            # 2. Boundary detection evaluation
            boundary = question_boundary_detector.evaluate_line(
                line=item.text,
                line_idx=i,
                next_line=next_text,
            )

            if boundary is not None:
                # Decide if this boundary starts a new question or continues current
                if current_qnum is not None:
                    # Current question is numbered
                    if boundary.question_number is not None:
                        if boundary.question_number != current_qnum:
                            # New numbered question
                            flush_current()
                            current_qnum = boundary.question_number
                            current_pages.append((item.page_number, item.page_id))
                            if boundary.remaining_text:
                                current_lines.append(boundary.remaining_text)
                        else:
                            # Redundant duplicate question number, continue
                            current_lines.append(boundary.remaining_text or item.text)
                            current_pages.append((item.page_number, item.page_id))
                    else:
                        # Unnumbered boundary inside an existing numbered question stem -> treat as stem continuation
                        current_lines.append(item.text)
                        current_pages.append((item.page_number, item.page_id))
                elif current_lines:
                    # Current question is unnumbered
                    flush_current()
                    current_qnum = boundary.question_number
                    current_pages.append((item.page_number, item.page_id))
                    if boundary.remaining_text:
                        current_lines.append(boundary.remaining_text)
                else:
                    # No active question currently
                    current_qnum = boundary.question_number
                    current_pages.append((item.page_number, item.page_id))
                    if boundary.remaining_text:
                        current_lines.append(boundary.remaining_text)
            else:
                # No boundary detected
                if current_lines or current_qnum is not None:
                    current_lines.append(item.text)
                    current_pages.append((item.page_number, item.page_id))
                # Otherwise, line is preamble before Question 1 (ignored)

        flush_current()
        return questions

    def extract_and_persist(
        self,
        document_id: uuid.UUID,
        db: Session,
    ) -> DocumentExtractionResult:
        """Extract questions from stored DocumentPages and atomically persist to database."""
        # 1. Fetch document pages in order
        pages = list(
            db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number.asc())
            ).all()
        )

        if not pages:
            logger.warning("No pages found for document %s during question extraction.", document_id)
            return DocumentExtractionResult(
                document_id=document_id,
                questions=[],
                total_questions=0,
                total_pages_processed=0,
            )

        # 2. Extract questions across pages
        extracted = self.extract_questions_from_pages(pages)

        # 3. Transactional delete-and-rebuild for document questions
        try:
            # Delete existing questions (cascades to options and sources)
            db.execute(delete(Question).where(Question.document_id == document_id))

            base_time = datetime.datetime.now(datetime.timezone.utc)
            for idx, eq in enumerate(extracted):
                confidence_score = 1.0 if eq.status == QuestionStatus.EXTRACTED else 0.7
                db_question = Question(
                    document_id=document_id,
                    question_number=eq.question_number,
                    question_text=eq.question_text,
                    question_type=eq.question_type,
                    status=eq.status,
                    confidence=confidence_score,
                    created_at=base_time + datetime.timedelta(milliseconds=idx),
                )
                db.add(db_question)
                db.flush()  # Populate db_question.id

                # Add options
                for opt in eq.options:
                    db_opt = QuestionOption(
                        question_id=db_question.id,
                        label=opt.label,
                        option_text=opt.text,
                        position=opt.position,
                    )
                    db.add(db_opt)

                # Add sources
                for seq, (p_num, p_id) in enumerate(eq.source_pages, start=1):
                    db_source = QuestionSource(
                        question_id=db_question.id,
                        document_page_id=p_id,
                        page_sequence=seq,
                    )
                    db.add(db_source)

            db.commit()
            logger.info(
                "Document %s extracted %d questions across %d pages.",
                document_id,
                len(extracted),
                len(pages),
            )
        except Exception as e:
            logger.error(
                "Failed to persist extracted questions for document %s: %s",
                document_id,
                e,
            )
            db.rollback()
            raise

        return DocumentExtractionResult(
            document_id=document_id,
            questions=extracted,
            total_questions=len(extracted),
            total_pages_processed=len(pages),
        )


question_extractor = QuestionExtractor()
