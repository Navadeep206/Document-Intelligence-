"""Document ingestion, retrieval, file download, and lifecycle endpoints."""

import logging
from pathlib import Path
from typing import Annotated, Optional
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.db.database import get_db
from app.db.models.answer import AnswerKey, AnswerMapping
from app.db.models.document import Document
from app.db.models.enums import (
    DocumentRole,
    DocumentStatus,
    ProcessingJobStatus,
    QuestionStatus,
    QuestionType,
    RelatedDocumentType,
    ReviewSeverity,
    ReviewStatus,
)
from app.db.models.page import DocumentPage
from app.db.models.processing_job import ProcessingJob
from app.db.models.question import Question, QuestionSource
from app.db.models.related_document import RelatedDocument
from app.db.models.review import ReviewItem
from app.db.models.user import User
from app.schemas.answer import (
    AnswerKeyResponse,
    AnswerKeySummaryResponse,
    AnswerMappingListResponse,
    AnswerMappingResponse,
    DocumentAnswersResponse,
)
from app.schemas.document import (
    DocumentListResponse,
    DocumentPageListResponse,
    DocumentPageResponse,
    DocumentProcessingStatusResponse,
    DocumentResponse,
    DocumentUploadAcceptedResponse,
    ProcessingJobResponse,
)
from app.schemas.question import QuestionListResponse, QuestionResponse
from app.schemas.related_document import (
    RelatedDocumentCreateRequest,
    RelatedDocumentListResponse,
    RelatedDocumentResponse,
)
from app.schemas.review import (
    DocumentReviewSummaryResponse,
    ReviewItemListResponse,
    ReviewItemResponse,
)
from app.services.answer_extraction import answer_extractor
from app.services.confidence.review_service import review_service
from app.services.file_validator import validate_and_read_upload
from app.services.storage import get_storage_service
from app.workers.tasks.document_processing import process_document

logger = logging.getLogger("document-intelligence-service")
router = APIRouter()


@router.post(
    "",
    response_model=DocumentUploadAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Document",
    description="Securely upload, register, and queue a PDF or image document for asynchronous extraction.",
)
@router.post(
    "/upload",
    response_model=DocumentUploadAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Document (Alias)",
    description="Securely upload, register, and queue a PDF or image document for asynchronous extraction.",
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Document binary (PDF, JPG, JPEG, PNG)")],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    document_role: Annotated[
        DocumentRole,
        Form(description="Functional examination role of the document"),
    ] = DocumentRole.UNKNOWN,
) -> DocumentUploadAcceptedResponse:
    """Validate, store, create database record, and enqueue background Celery processing job."""
    # 1. Validate file extension, MIME type, signature, and size limit
    doc_type, safe_original_filename, mime_type, file_content, file_size = (
        await validate_and_read_upload(file)
    )

    storage = get_storage_service()
    ext = Path(safe_original_filename).suffix

    # 2. Persist to storage with randomized UUID naming
    storage_path, written_size = storage.save(file_content, ext)

    # 3. Create database document and initial processing job
    document = Document(
        owner_id=current_user.id,
        filename=safe_original_filename,
        storage_path=storage_path,
        mime_type=mime_type,
        document_type=doc_type,
        document_role=document_role,
        file_size=written_size,
        status=DocumentStatus.QUEUED,
    )

    try:
        db.add(document)
        db.flush()

        job = ProcessingJob(
            document_id=document.id,
            status=ProcessingJobStatus.PENDING,
            attempt=1,
        )
        db.add(job)
        db.commit()
        db.refresh(document)
        db.refresh(job)
    except Exception as exc:
        db.rollback()
        logger.error(
            "Database error during document upload. Cleaning up file '%s': %s",
            storage_path,
            exc,
        )
        storage.delete(storage_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Failed to persist document and processing job metadata",
            },
        )

    # 4. Dispatch Celery task safely after DB commit
    try:
        task = process_document.delay(str(document.id), str(job.id))
        job.task_id = task.id
        db.commit()
        logger.info(
            "Document %s uploaded and enqueued (job: %s, task: %s, role: %s, size: %d bytes)",
            document.id,
            job.id,
            task.id,
            document.document_role,
            document.file_size,
        )
    except Exception as exc:
        logger.error(
            "Failed to enqueue Celery task for document %s, job %s: %s",
            document.id,
            job.id,
            exc,
        )
        job.status = ProcessingJobStatus.FAILED
        job.error_message = f"Task dispatch failed: {exc}"
        document.status = DocumentStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "TASK_DISPATCH_FAILED",
                "message": "Failed to queue document for processing",
            },
        )

    return DocumentUploadAcceptedResponse(
        id=document.id,
        filename=document.filename,
        status=document.status,
        job_id=job.id,
        created_at=document.created_at,
    )



@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List User Documents",
    description="Retrieve a paginated list of documents owned by the authenticated user.",
)
def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> DocumentListResponse:
    """Return paginated list of current user's documents."""
    base_query = select(Document).where(Document.owner_id == current_user.id)

    total = db.scalar(
        select(func.count()).select_from(base_query.subquery())
    ) or 0

    docs = db.scalars(
        base_query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in docs],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document Metadata",
    description="Retrieve document metadata. Non-owned documents return 404 to prevent enumeration.",
)
def get_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentResponse:
    """Retrieve document metadata for the owning user."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    q_count = db.scalar(
        select(func.count()).select_from(Question).where(Question.document_id == doc.id)
    ) or 0
    r_count = db.scalar(
        select(func.count()).select_from(ReviewItem).where(ReviewItem.document_id == doc.id)
    ) or 0

    resp = DocumentResponse.model_validate(doc)
    resp.question_count = q_count
    resp.review_count = r_count
    return resp


@router.get(
    "/{document_id}/status",
    response_model=DocumentProcessingStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document Processing Status",
    description="Retrieve real-time processing status and current job details for an authorized document.",
)
def get_document_status(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentProcessingStatusResponse:
    """Retrieve processing lifecycle status and active job details."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    job = db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
    )

    job_resp = None
    if job:
        job_resp = ProcessingJobResponse(
            id=job.id,
            status=job.status.value if hasattr(job.status, "value") else str(job.status),
            attempt=job.attempt,
            task_id=job.task_id,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )

    pages_processed = db.scalar(
        select(func.count()).select_from(DocumentPage).where(DocumentPage.document_id == doc.id)
    ) or 0
    total_pages = doc.page_count if doc.page_count is not None and doc.page_count > 0 else (pages_processed if pages_processed > 0 else None)
    questions_extracted = db.scalar(
        select(func.count()).select_from(Question).where(Question.document_id == doc.id)
    ) or 0
    review_required = db.scalar(
        select(func.count()).select_from(ReviewItem).where(
            ReviewItem.document_id == doc.id,
            ReviewItem.status == ReviewStatus.OPEN,
        )
    ) or 0

    return DocumentProcessingStatusResponse(
        document_id=doc.id,
        status=doc.status,
        document_status=doc.status,
        page_count=doc.page_count,
        pages_processed=pages_processed,
        total_pages=total_pages,
        questions_extracted=questions_extracted,
        review_required=review_required,
        job=job_resp,
    )


@router.get(
    "/{document_id}/pages",
    response_model=DocumentPageListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Extracted Document Pages",
    description="Retrieve all extracted pages with normalized text and OCR telemetry for an authorized document.",
)
def get_document_pages(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentPageListResponse:
    """Retrieve extracted page text and OCR telemetry for document owner."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number.asc())
    ).all()

    return DocumentPageListResponse(
        document_id=doc.id,
        total_pages=len(pages),
        items=[DocumentPageResponse.model_validate(p) for p in pages],
    )


@router.get(
    "/{document_id}/questions",
    response_model=QuestionListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Extracted Questions",
    description="Retrieve paginated structured questions, options, and source provenance for an authorized document with optional filtering.",
)
def get_document_questions(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    status_filter: Annotated[Optional[QuestionStatus], Query(alias="status", description="Filter by question status")] = None,
    question_type: Annotated[Optional[QuestionType], Query(description="Filter by question type")] = None,
    review_required: Annotated[Optional[bool], Query(description="Filter questions requiring review")] = None,
    page_number: Annotated[Optional[int], Query(ge=1, description="Filter questions on source page")] = None,
) -> QuestionListResponse:
    """Retrieve structured questions with options and source page references for document owner."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    base_query = select(Question).where(Question.document_id == document_id)

    if status_filter is not None:
        base_query = base_query.where(Question.status == status_filter)
    if question_type is not None:
        base_query = base_query.where(Question.question_type == question_type)
    if review_required is not None:
        base_query = base_query.where(Question.review_required == review_required)
    if page_number is not None:
        base_query = (
            base_query.join(Question.sources)
            .join(DocumentPage, QuestionSource.document_page_id == DocumentPage.id)
            .where(DocumentPage.page_number == page_number)
        )

    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    questions = list(
        db.scalars(
            base_query.options(
                selectinload(Question.options),
                selectinload(Question.sources),
                selectinload(Question.review_items),
            )
            .order_by(Question.created_at.asc(), Question.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )

    return QuestionListResponse(
        document_id=doc.id,
        items=[QuestionResponse.model_validate(q) for q in questions],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post(
    "/{document_id}/related",
    response_model=RelatedDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Related Document Association",
    description="Establish an explicit relationship between two documents owned by the user (e.g., Question Paper -> Answer Key).",
)
def create_related_document(
    document_id: uuid.UUID,
    payload: RelatedDocumentCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RelatedDocumentResponse:
    """Relate two documents owned by the authenticated user and trigger answer association when applicable."""
    # 1. Prevent self-relationship
    if document_id == payload.related_document_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_RELATIONSHIP",
                "message": "Cannot create relationship between a document and itself",
            },
        )

    # 2. Verify source document exists and is owned by current user
    source_doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    if source_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Source document not found",
            },
        )

    # 3. Verify target related document exists and is owned by current user
    target_doc = db.scalar(
        select(Document).where(
            Document.id == payload.related_document_id,
            Document.owner_id == current_user.id,
        )
    )
    if target_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Target related document not found",
            },
        )

    # 4. Check for duplicate relationship
    existing = db.scalar(
        select(RelatedDocument).where(
            RelatedDocument.document_id == document_id,
            RelatedDocument.related_document_id == payload.related_document_id,
            RelatedDocument.relationship_type == payload.relationship_type,
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_RELATIONSHIP",
                "message": "Relationship between these documents already exists",
            },
        )

    # 5. Persist relationship
    rel = RelatedDocument(
        document_id=document_id,
        related_document_id=payload.related_document_id,
        relationship_type=payload.relationship_type,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)

    # 6. Trigger answer-key extraction & question association if ANSWER_KEY relationship
    if payload.relationship_type == RelatedDocumentType.ANSWER_KEY:
        try:
            answer_extractor.extract_and_associate(
                question_document_id=document_id,
                source_document_id=payload.related_document_id,
                db=db,
            )
        except Exception as exc:
            logger.error(
                "Failed associating answer key %s with question document %s: %s",
                payload.related_document_id,
                document_id,
                exc,
            )

    return RelatedDocumentResponse.model_validate(rel)


@router.get(
    "/{document_id}/related",
    response_model=RelatedDocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Related Documents",
    description="Retrieve all directional document relationships for an authorized document.",
)
def get_related_documents(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RelatedDocumentListResponse:
    """Retrieve all related documents for document owner."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    rels = list(
        db.scalars(
            select(RelatedDocument)
            .where(RelatedDocument.document_id == document_id)
            .order_by(RelatedDocument.created_at.asc())
        ).all()
    )

    return RelatedDocumentListResponse(
        document_id=doc.id,
        total=len(rels),
        items=[RelatedDocumentResponse.model_validate(r) for r in rels],
    )


@router.get(
    "/{document_id}/answers",
    response_model=DocumentAnswersResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document Answers",
    description="Retrieve all extracted answer mappings, confidence scores, and source pages for an authorized document.",
)
def get_document_answers(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentAnswersResponse:
    """Retrieve extracted answers and answer key for document owner."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    answer_key = db.scalar(
        select(AnswerKey)
        .where(AnswerKey.document_id == document_id)
        .options(selectinload(AnswerKey.mappings))
        .order_by(AnswerKey.created_at.desc())
    )

    if not answer_key:
        return DocumentAnswersResponse(
            document_id=doc.id,
            answer_key=None,
            answers=[],
        )

    return DocumentAnswersResponse(
        document_id=doc.id,
        answer_key=AnswerKeyResponse.model_validate(answer_key),
        answers=[AnswerMappingResponse.model_validate(m) for m in answer_key.mappings],
    )


@router.get(
    "/{document_id}/answer-key",
    response_model=AnswerKeySummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Answer Key Summary",
    description="Retrieve telemetry metadata, mapping counts, and matching statistics for an authorized document's answer key.",
)
def get_answer_key_summary(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AnswerKeySummaryResponse:
    """Retrieve summary metrics for an answer key."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    answer_key = db.scalar(
        select(AnswerKey)
        .where(AnswerKey.document_id == document_id)
        .options(selectinload(AnswerKey.mappings))
        .order_by(AnswerKey.created_at.desc())
    )

    if not answer_key:
        return AnswerKeySummaryResponse(
            document_id=doc.id,
            answer_key_id=None,
            total_mappings=0,
            matched_count=0,
            unmatched_count=0,
        )

    matched = sum(1 for m in answer_key.mappings if m.question_id is not None)
    unmatched = len(answer_key.mappings) - matched

    return AnswerKeySummaryResponse(
        document_id=doc.id,
        answer_key_id=answer_key.id,
        source_document_id=answer_key.source_document_id,
        confidence=answer_key.confidence,
        total_mappings=len(answer_key.mappings),
        matched_count=matched,
        unmatched_count=unmatched,
    )


@router.get(
    "/{document_id}/answer-mappings",
    response_model=AnswerMappingListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document Answer Mappings",
    description="Retrieve paginated answer mappings with MATCHED, UNMATCHED, AMBIGUOUS status distinctions.",
)
def get_document_answer_mappings(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    status_filter: Annotated[Optional[str], Query(alias="status", description="Filter by match status (MATCHED, UNMATCHED)")] = None,
) -> AnswerMappingListResponse:
    """Retrieve answer mappings for document owner."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    base_query = (
        select(AnswerMapping)
        .join(AnswerKey, AnswerMapping.answer_key_id == AnswerKey.id)
        .where(AnswerKey.document_id == document_id)
    )

    if status_filter:
        sf = status_filter.upper().strip()
        if sf == "MATCHED":
            base_query = base_query.where(AnswerMapping.question_id.is_not(None))
        elif sf == "UNMATCHED":
            base_query = base_query.where(AnswerMapping.question_id.is_(None))

    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    mappings = list(
        db.scalars(
            base_query.order_by(AnswerMapping.created_at.asc(), AnswerMapping.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )

    items = []
    for m in mappings:
        item = AnswerMappingResponse.model_validate(m)
        if m.question_id is not None:
            item.status = "MATCHED"
        else:
            item.status = "UNMATCHED"
        items.append(item)

    return AnswerMappingListResponse(
        document_id=doc.id,
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/{document_id}/reviews",
    response_model=ReviewItemListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document Review Items",
    description="Retrieve paginated human review issues for an authorized document with optional status, severity, and reason filters.",
)
def get_document_reviews(
    document_id: uuid.UUID,
    status_filter: Annotated[Optional[ReviewStatus], Query(alias="status")] = None,
    severity: Optional[ReviewSeverity] = None,
    reason: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ReviewItemListResponse:
    """List paginated review issues for document owner."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    query = select(ReviewItem).where(ReviewItem.document_id == document_id)
    if status_filter:
        query = query.where(ReviewItem.status == status_filter)
    if severity:
        query = query.where(ReviewItem.severity == severity)
    if reason:
        query = query.where(ReviewItem.reason == reason)

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(ReviewItem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return ReviewItemListResponse(
        items=[ReviewItemResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{document_id}/reviews/summary",
    response_model=DocumentReviewSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document Review Summary",
    description="Retrieve aggregated review and confidence metrics for an authorized document.",
)
def get_document_review_summary(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentReviewSummaryResponse:
    """Retrieve aggregate review statistics for document owner."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    summary = review_service.get_document_summary(document_id, db)
    return DocumentReviewSummaryResponse(
        document_id=summary.document_id,
        total_questions=summary.total_questions,
        high_confidence_questions=summary.high_confidence_questions,
        partial_questions=summary.partial_questions,
        review_required_questions=summary.review_required_questions,
        open_review_items=summary.open_review_items,
        resolved_review_items=summary.resolved_review_items,
        ignored_review_items=summary.ignored_review_items,
        unmatched_answers=summary.unmatched_answers,
        ambiguous_answers=summary.ambiguous_answers,
    )



@router.get(
    "/{document_id}/file",

    status_code=status.HTTP_200_OK,
    summary="Download Original Document File",
    description="Securely download the raw original file for an authorized document.",
)
def download_document_file(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    """Stream protected document binary to the verified owner."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    storage = get_storage_service()
    try:
        abs_path = storage.get_absolute_path(doc.storage_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Storage missing for document %s: %s", doc.id, exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "FILE_NOT_FOUND_ON_STORAGE",
                "message": "Physical file is unavailable on storage system",
            },
        )

    return FileResponse(
        path=abs_path,
        filename=doc.filename,
        media_type=doc.mime_type,
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Document",
    description="Permanently delete a document, its database record, and its physical storage file.",
)
def delete_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete document owned by user and purge physical storage."""
    doc = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    storage_path = doc.storage_path

    # Delete database record first
    db.delete(doc)
    db.commit()

    # Delete storage file
    storage = get_storage_service()
    storage.delete(storage_path)

    logger.info("Document %s deleted by user %s", document_id, current_user.id)
