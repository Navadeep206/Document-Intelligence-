"""Document processing pipeline service orchestrating page extraction, digital text, and OCR."""

import datetime
import logging
from pathlib import Path
import time
from typing import Any, Optional
import uuid

import fitz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentRole, DocumentStatus, RelatedDocumentType
from app.db.models.page import DocumentPage
from app.db.models.related_document import RelatedDocument
from app.services.answer_extraction import AnswerExtractor, answer_extractor
from app.services.confidence.review_service import ReviewService, review_service
from app.services.document_inspector import (
    CorruptDocumentError,
    DocumentInspector,
    UnreadableDocumentError,
    document_inspector,
)
from app.services.extraction import QuestionExtractor, question_extractor
from app.services.image_service import ImageService, image_service
from app.services.ocr_service import OCRService, ocr_service
from app.services.pdf_service import PDFService, pdf_service
from app.services.preprocessing_service import PreprocessingService, preprocessing_service
from app.services.storage import get_storage_service
from app.services.text_normalizer import normalize_extracted_text

logger = logging.getLogger("document-intelligence-service")


class DocumentProcessor:
    """Core domain service orchestrating page inspection, digital extraction, OCR, and persistence."""

    def __init__(
        self,
        inspector: Optional[DocumentInspector] = None,
        pdf_svc: Optional[PDFService] = None,
        img_svc: Optional[ImageService] = None,
        preproc_svc: Optional[PreprocessingService] = None,
        ocr_svc: Optional[OCRService] = None,
        extractor: Optional[QuestionExtractor] = None,
        answer_extractor_svc: Optional[AnswerExtractor] = None,
        review_svc: Optional[ReviewService] = None,
    ):
        self.inspector = inspector or document_inspector
        self.pdf_service = pdf_svc or pdf_service
        self.image_service = img_svc or image_service
        self.preprocessing_service = preproc_svc or preprocessing_service
        self.ocr_service = ocr_svc or ocr_service
        self.question_extractor = extractor or question_extractor
        self.answer_extractor = answer_extractor_svc or answer_extractor
        self.review_service = review_svc or review_service

    def process(
        self,
        document_id: uuid.UUID,
        storage_path: str,
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        """Execute the end-to-end page extraction and text processing pipeline."""
        start_time = time.perf_counter()
        logger.info("Starting processing pipeline for document %s (storage: %s)", document_id, storage_path)

        storage = get_storage_service()
        try:
            abs_path: Path = storage.get_absolute_path(storage_path)
        except Exception as exc:
            logger.error("Failed to resolve storage path '%s': %s", storage_path, exc)
            raise FileNotFoundError(f"Storage path '{storage_path}' could not be resolved") from exc

        if not abs_path.is_file():
            logger.error("Physical document file missing at '%s'", abs_path)
            raise FileNotFoundError(f"Physical file missing for document {document_id}")

        session_created = False
        if db is None:
            db = SessionLocal()
            session_created = True

        try:
            # 1. Inspect document structure, page count, and text status
            doc_record = db.scalar(select(Document).where(Document.id == document_id))
            if not doc_record:
                raise ValueError(f"Document {document_id} not found in database")

            inspection = self.inspector.inspect(abs_path)
            doc_record.page_count = inspection.page_count
            db.commit()

            successful_pages = 0
            failed_pages = 0
            page_summaries: list[dict[str, Any]] = []

            # 2. Process page by page
            if inspection.format == "PDF":
                fitz_doc = fitz.open(abs_path)
                try:
                    for page_idx in range(inspection.page_count):
                        page_num = page_idx + 1
                        page_start = time.perf_counter()
                        try:
                            fitz_page = fitz_doc.load_page(page_idx)
                            raw_text, is_sufficient = self.pdf_service.extract_native_text(fitz_page)

                            if is_sufficient:
                                # Native digital extraction path
                                mode = "NATIVE"
                                ocr_used = False
                                ocr_confidence = None
                                rotation = fitz_page.rotation
                                cleaned_text = normalize_extracted_text(raw_text)
                            else:
                                # OCR fallback path for scanned or low-text pages
                                mode = "OCR"
                                ocr_used = True
                                page_img = self.pdf_service.render_page_to_image(fitz_page)
                                try:
                                    prep_img = self.preprocessing_service.preprocess_image(page_img)
                                    try:
                                        ocr_res = self.ocr_service.extract_text(prep_img)
                                        ocr_confidence = ocr_res.confidence
                                        rotation = ocr_res.rotation if ocr_res.rotation else fitz_page.rotation
                                        cleaned_text = normalize_extracted_text(ocr_res.text)
                                    finally:
                                        prep_img.close()
                                finally:
                                    page_img.close()

                            # Persist or update DocumentPage
                            self._upsert_page(
                                db=db,
                                document_id=document_id,
                                page_number=page_num,
                                text_content=cleaned_text,
                                ocr_used=ocr_used,
                                ocr_confidence=ocr_confidence,
                                rotation=rotation,
                            )
                            db.commit()
                            successful_pages += 1

                            page_duration_ms = int((time.perf_counter() - page_start) * 1000)
                            logger.info(
                                "Document %s page %d processed: mode=%s, ocr_conf=%s, rot=%s, duration_ms=%d",
                                document_id,
                                page_num,
                                mode,
                                ocr_confidence,
                                rotation,
                                page_duration_ms,
                            )
                            page_summaries.append({
                                "page_number": page_num,
                                "mode": mode,
                                "ocr_used": ocr_used,
                                "ocr_confidence": ocr_confidence,
                                "char_count": len(cleaned_text),
                                "duration_ms": page_duration_ms,
                            })

                        except Exception as page_err:
                            logger.error(
                                "Failed processing page %d for document %s: %s",
                                page_num,
                                document_id,
                                page_err,
                            )
                            failed_pages += 1
                            # Persist empty page record so sequence is maintained
                            try:
                                self._upsert_page(
                                    db=db,
                                    document_id=document_id,
                                    page_number=page_num,
                                    text_content="",
                                    ocr_used=None,
                                    ocr_confidence=None,
                                    rotation=0,
                                )
                                db.commit()
                            except Exception as db_err:
                                logger.error("Failed recording error placeholder for page %d: %s", page_num, db_err)
                                db.rollback()
                finally:
                    fitz_doc.close()

            else:
                # Image formats (JPG, JPEG, PNG) -> single page 1
                page_start = time.perf_counter()
                try:
                    raw_img = self.image_service.load_image(abs_path)
                    try:
                        prep_img = self.preprocessing_service.preprocess_image(raw_img)
                        try:
                            ocr_res = self.ocr_service.extract_text(prep_img)
                            ocr_used = True
                            ocr_confidence = ocr_res.confidence
                            rotation = ocr_res.rotation
                            cleaned_text = normalize_extracted_text(ocr_res.text)
                        finally:
                            prep_img.close()
                    finally:
                        raw_img.close()

                    self._upsert_page(
                        db=db,
                        document_id=document_id,
                        page_number=1,
                        text_content=cleaned_text,
                        ocr_used=ocr_used,
                        ocr_confidence=ocr_confidence,
                        rotation=rotation,
                    )
                    db.commit()
                    successful_pages += 1

                    page_duration_ms = int((time.perf_counter() - page_start) * 1000)
                    logger.info(
                        "Document %s image processed: mode=OCR, ocr_conf=%s, rot=%s, duration_ms=%d",
                        document_id,
                        ocr_confidence,
                        rotation,
                        page_duration_ms,
                    )
                    page_summaries.append({
                        "page_number": 1,
                        "mode": "OCR",
                        "ocr_used": ocr_used,
                        "ocr_confidence": ocr_confidence,
                        "char_count": len(cleaned_text),
                        "duration_ms": page_duration_ms,
                    })

                except Exception as img_err:
                    logger.error("Failed processing image document %s: %s", document_id, img_err)
                    failed_pages += 1

            # 3. Determine final document processing status
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            doc_record.processed_at = now_utc

            # 3. Extract structured questions from processed pages (Phase 6)
            extracted_questions_count = 0
            if successful_pages > 0 and doc_record.document_role != DocumentRole.ANSWER_KEY:
                try:
                    extraction_res = self.question_extractor.extract_and_persist(
                        document_id=document_id,
                        db=db,
                    )
                    extracted_questions_count = extraction_res.total_questions
                    logger.info(
                        "Extracted %d questions for document %s",
                        extracted_questions_count,
                        document_id,
                    )
                except Exception as extract_err:
                    logger.error(
                        "Question extraction failed for document %s: %s",
                        document_id,
                        extract_err,
                    )

            # 4. Answer-key detection & association (Phase 7)
            answer_key_info = {"extracted": False, "matched_count": 0, "total_entries": 0}
            if successful_pages > 0:
                try:
                    if doc_record.document_role == DocumentRole.ANSWER_KEY:
                        # Separate answer-key document: check if related question paper exists
                        related_paper = db.scalar(
                            select(RelatedDocument).where(
                                RelatedDocument.related_document_id == document_id,
                                RelatedDocument.relationship_type == RelatedDocumentType.ANSWER_KEY,
                            )
                        )
                        if related_paper:
                            ans_res = self.answer_extractor.extract_and_associate(
                                question_document_id=related_paper.document_id,
                                source_document_id=document_id,
                                db=db,
                            )
                            answer_key_info = {
                                "extracted": True,
                                "matched_count": ans_res.matched_count,
                                "total_entries": ans_res.total_entries,
                            }
                        else:
                            # Parse candidate answers for this document itself (pending relationship)
                            ans_res = self.answer_extractor.extract_and_associate(
                                question_document_id=document_id,
                                source_document_id=document_id,
                                db=db,
                            )
                            answer_key_info = {
                                "extracted": True,
                                "matched_count": 0,
                                "total_entries": ans_res.total_entries,
                            }
                    else:
                        # Same-document answer key check:
                        ans_res = self.answer_extractor.extract_and_associate(
                            question_document_id=document_id,
                            source_document_id=document_id,
                            db=db,
                        )
                        if ans_res.total_entries > 0:
                            answer_key_info = {
                                "extracted": True,
                                "matched_count": ans_res.matched_count,
                                "total_entries": ans_res.total_entries,
                            }
                except Exception as ans_err:
                    logger.error(
                        "Answer key extraction failed for document %s: %s",
                        document_id,
                        ans_err,
                    )

            # 5. Confidence calculation & human review synchronization (Phase 8)
            review_summary_info = {
                "open_review_items": 0,
                "review_required_questions": 0,
                "high_confidence_questions": 0,
            }
            if extracted_questions_count > 0:
                try:
                    summary = self.review_service.sync_document_reviews(
                        document_id=document_id,
                        db=db,
                    )
                    review_summary_info = {
                        "open_review_items": summary.open_review_items,
                        "review_required_questions": summary.review_required_questions,
                        "high_confidence_questions": summary.high_confidence_questions,
                    }
                    logger.info(
                        "Confidence & review evaluated for document %s: open_reviews=%d, review_req=%d, high_conf=%d",
                        document_id,
                        summary.open_review_items,
                        summary.review_required_questions,
                        summary.high_confidence_questions,
                    )
                except Exception as rev_err:
                    logger.error(
                        "Confidence/review sync failed for document %s: %s",
                        document_id,
                        rev_err,
                    )

            if successful_pages == inspection.page_count:
                final_status = DocumentStatus.COMPLETED
            elif successful_pages > 0 and failed_pages > 0:
                final_status = DocumentStatus.PARTIAL
            else:
                final_status = DocumentStatus.FAILED

            doc_record.status = final_status
            db.commit()

            total_duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info(
                "Document %s processing finished: status=%s, total_pages=%d, success=%d, failed=%d, extracted_q=%d, ans_matched=%d, open_reviews=%d, duration_ms=%d",
                document_id,
                final_status.value,
                inspection.page_count,
                successful_pages,
                failed_pages,
                extracted_questions_count,
                answer_key_info["matched_count"],
                review_summary_info["open_review_items"],
                total_duration_ms,
            )

            return {
                "success": final_status in (DocumentStatus.COMPLETED, DocumentStatus.PARTIAL),
                "document_id": str(document_id),
                "document_status": final_status.value,
                "page_count": inspection.page_count,
                "successful_pages": successful_pages,
                "failed_pages": failed_pages,
                "extracted_questions": extracted_questions_count,
                "answers": answer_key_info,
                "review_summary": review_summary_info,
                "duration_ms": total_duration_ms,
                "pages": page_summaries,
            }

        finally:
            if session_created:
                db.close()

    def _upsert_page(
        self,
        db: Session,
        document_id: uuid.UUID,
        page_number: int,
        text_content: str,
        ocr_used: Optional[bool],
        ocr_confidence: Optional[float],
        rotation: Optional[int],
    ) -> DocumentPage:
        """Insert or update DocumentPage entity preserving unique page constraints."""
        existing_page = db.scalar(
            select(DocumentPage).where(
                DocumentPage.document_id == document_id,
                DocumentPage.page_number == page_number,
            )
        )

        if existing_page:
            existing_page.text_content = text_content
            existing_page.ocr_used = ocr_used
            existing_page.ocr_confidence = ocr_confidence
            existing_page.rotation = rotation
            return existing_page
        else:
            new_page = DocumentPage(
                document_id=document_id,
                page_number=page_number,
                text_content=text_content,
                ocr_used=ocr_used,
                ocr_confidence=ocr_confidence,
                rotation=rotation,
            )
            db.add(new_page)
            return new_page


document_processor = DocumentProcessor()
