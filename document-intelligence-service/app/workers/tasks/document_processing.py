import datetime
import logging
from typing import Any
import uuid

from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentStatus, ProcessingJobStatus
from app.db.models.processing_job import ProcessingJob
from app.services.document_inspector import CorruptDocumentError, UnreadableDocumentError
from app.services.document_processor import document_processor
from app.services.storage import get_storage_service
from app.workers.celery_app import celery_app

logger = logging.getLogger("document-intelligence-service")
settings = get_settings()


@celery_app.task(
    bind=True,
    name="document_processing.process_document",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
)
def process_document(self, document_id: str, job_id: str) -> dict[str, Any]:
    """Execute asynchronous document intelligence processing pipeline with retry and idempotency."""
    doc_uuid = uuid.UUID(str(document_id))
    job_uuid = uuid.UUID(str(job_id))

    logger.info(
        "Celery task received: process_document [task_id=%s, doc=%s, job=%s, attempt=%d]",
        self.request.id,
        doc_uuid,
        job_uuid,
        self.request.retries + 1,
    )

    db: Session = SessionLocal()
    try:
        # 1. Fetch processing job
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_uuid))
        if not job:
            logger.error("Processing job %s not found in database. Aborting.", job_uuid)
            return {"status": "failed", "reason": "job_not_found"}

        # 2. Idempotency Check: if job is already COMPLETED, exit safely
        if job.status == ProcessingJobStatus.COMPLETED:
            logger.info(
                "Idempotency check: Job %s is already COMPLETED. Skipping redundant execution.",
                job_uuid,
            )
            return {"status": "already_completed", "job_id": str(job_uuid)}

        # 3. Fetch document
        doc = db.scalar(select(Document).where(Document.id == doc_uuid))
        if not doc:
            logger.error("Document %s not found in database. Marking job %s failed.", doc_uuid, job_uuid)
            job.status = ProcessingJobStatus.FAILED
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            job.error_message = "Document record not found in database"
            db.commit()
            return {"status": "failed", "reason": "document_not_found"}

        # 4. Verify storage file exists (Permanent failure check)
        storage = get_storage_service()
        if not storage.exists(doc.storage_path):
            error_msg = f"Document storage file '{doc.storage_path}' is missing from storage"
            logger.error("Permanent error for document %s: %s", doc_uuid, error_msg)
            job.status = ProcessingJobStatus.FAILED
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            job.error_message = error_msg
            doc.status = DocumentStatus.FAILED
            doc.error_message = error_msg
            db.commit()
            return {"status": "failed", "reason": "file_missing"}

        # 5. Transition state to RUNNING and PROCESSING
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        job.status = ProcessingJobStatus.RUNNING
        job.attempt = self.request.retries + 1
        job.task_id = self.request.id
        if not job.started_at:
            job.started_at = now_utc
        doc.status = DocumentStatus.PROCESSING
        db.commit()

        logger.info(
            "Document %s and Job %s transitioned to PROCESSING/RUNNING (task_id=%s)",
            doc_uuid,
            job_uuid,
            self.request.id,
        )

        # 6. Execute document ingestion and text extraction pipeline
        processor_result = document_processor.process(
            document_id=doc_uuid,
            storage_path=doc.storage_path,
            db=db,
        )

        # 7. Transition job state based on extraction result
        now_completed = datetime.datetime.now(datetime.timezone.utc)
        job.completed_at = now_completed

        doc_final_status = processor_result.get("document_status", "COMPLETED")
        if doc_final_status in ("COMPLETED", "PARTIAL"):
            job.status = ProcessingJobStatus.COMPLETED
            job.error_message = (
                f"Partially completed with {processor_result.get('failed_pages', 0)} page failure(s)"
                if doc_final_status == "PARTIAL"
                else None
            )
        else:
            job.status = ProcessingJobStatus.FAILED
            job.error_message = "All document pages failed extraction"

        db.commit()

        logger.info(
            "Document %s and Job %s successfully finished with status=%s (task_id=%s)",
            doc_uuid,
            job_uuid,
            job.status.value,
            self.request.id,
        )

        return {
            "status": job.status.value.lower(),
            "document_id": str(doc_uuid),
            "job_id": str(job_uuid),
            "result": processor_result,
        }

    except (FileNotFoundError, ValueError, CorruptDocumentError, UnreadableDocumentError) as perm_exc:
        # Non-retryable permanent domain failure
        logger.error(
            "Permanent failure processing document %s [job=%s]: %s",
            doc_uuid,
            job_uuid,
            perm_exc,
        )

        try:
            now_failed = datetime.datetime.now(datetime.timezone.utc)
            job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_uuid))
            doc = db.scalar(select(Document).where(Document.id == doc_uuid))
            if job:
                job.status = ProcessingJobStatus.FAILED
                job.completed_at = now_failed
                job.error_message = str(perm_exc)
            if doc:
                doc.status = DocumentStatus.FAILED
                doc.error_message = str(perm_exc)
            db.commit()
        except Exception as db_err:
            logger.error("Failed to commit permanent failure state: %s", db_err)
            db.rollback()
        return {"status": "failed", "error": str(perm_exc)}

    except (OperationalError, SQLAlchemyError, Exception) as transient_exc:
        # Transient failure: apply controlled exponential backoff retry
        logger.warning(
            "Transient error in document processing [doc=%s, job=%s, attempt=%d/%d]: %s",
            doc_uuid,
            job_uuid,
            self.request.retries + 1,
            self.max_retries,
            transient_exc,
        )
        db.rollback()

        if self.request.retries < self.max_retries:
            countdown = settings.CELERY_TASK_RETRY_BACKOFF * (2 ** self.request.retries)
            logger.info(
                "Scheduling Celery task retry in %d seconds for job %s",
                countdown,
                job_uuid,
            )
            raise self.retry(exc=transient_exc, countdown=countdown)
        else:
            logger.error(
                "Max retries (%d) exhausted for document %s [job=%s]: %s",
                self.max_retries,
                doc_uuid,
                job_uuid,
                transient_exc,
            )
            try:
                now_failed = datetime.datetime.now(datetime.timezone.utc)
                job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_uuid))
                doc = db.scalar(select(Document).where(Document.id == doc_uuid))
                if job:
                    job.status = ProcessingJobStatus.FAILED
                    job.completed_at = now_failed
                    job.error_message = f"Processing failed after {self.max_retries} retries"
                if doc:
                    doc.status = DocumentStatus.FAILED
                    doc.error_message = f"Processing failed after {self.max_retries} retries"
                db.commit()
            except Exception as db_err:
                logger.error("Failed to persist exhausted retries state: %s", db_err)
                db.rollback()
            return {"status": "failed", "error": "Max retries exceeded"}


    finally:
        db.close()
