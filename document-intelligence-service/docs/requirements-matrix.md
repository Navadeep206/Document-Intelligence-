# Assignment Requirements Traceability Matrix

This document maps all core assignment requirements for the **Document Intelligence & Question Extraction Service** to the actual verified backend implementation, code files, and automated tests.

---

## Traceability Matrix

| Requirement | Implementation Component | Endpoint / Service File | Automated Test File | Status | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Project Foundation & Config** | FastAPI application factory, Pydantic v2 Settings | `app/main.py`<br>`app/core/config.py` | `tests/test_health.py` | **Complete** | Health probes (`/health`, `/health/ready`), CORS, structured logging. |
| **Database & Schema Architecture** | PostgreSQL / SQLAlchemy 2.0 ORM + Alembic migrations | `app/db/base.py`<br>`app/db/models/` | `tests/test_models.py` | **Complete** | 11 relational tables, UUID primary keys, normalized foreign keys, ON DELETE CASCADE. |
| **Authentication (Argon2id + JWT)** | Passlib / Argon2-cffi password hashing, PyJWT bearer tokens | `app/core/security.py`<br>`app/api/v1/auth.py` | `tests/test_auth.py` | **Complete** | `/register`, `/login`, `/me` with RFC-7519 compliant JWT tokens, 30-minute expiry. |
| **Authorization & Tenant Isolation** | Dependency injection user context, ownership filters | `app/core/deps.py`<br>`app/api/v1/documents.py` | `tests/integration/test_authorization_matrix.py` | **Complete** | Strict cross-user isolation. User B receives 404 for User A documents, questions, and reviews. |
| **Secure File Upload & Validation** | Magic-byte checking, MIME detection, path traversal defense | `app/services/file_validator.py`<br>`app/api/v1/documents.py` | `tests/unit/test_file_validation.py`<br>`tests/test_documents.py` | **Complete** | Rejects non-PDF/image files, spoofed headers, oversized files (>25MB), sanitizes filenames via UUID. |
| **Local Storage Abstraction** | Local disk driver with path isolation & cleanup | `app/services/storage.py` | `tests/test_documents.py` | **Complete** | Abstracted interface (`save`, `get`, `delete`, `exists`), easily swappable for S3/MinIO. |
| **Asynchronous Processing Pipeline** | Redis broker + Celery distributed background worker | `app/workers/celery_app.py`<br>`app/workers/tasks.py`<br>`app/services/document_processor.py` | `tests/test_pipeline.py`<br>`tests/integration/test_api_lifecycle.py` | **Complete** | Fast 202 Accepted upload response; processing jobs track `PENDING` $\to$ `PROCESSING` $\to$ `COMPLETED`/`FAILED`. |
| **PDF Extraction & Rendering** | PyMuPDF (fitz) text and raster image extraction | `app/services/pdf_service.py`<br>`app/services/document_inspector.py` | `tests/test_page_processing.py` | **Complete** | Multi-page text extraction, coordinate bounding boxes, page rasterization for OCR. |
| **OCR Fallback & Image Ingestion** | Tesseract OCR + image preprocessing (grayscale, Otsu threshold) | `app/services/ocr_service.py`<br>`app/services/preprocessing_service.py` | `tests/test_page_processing.py` | **Complete** | Fallback triggered when native PDF text < 20 chars; direct OCR for JPEG/PNG image uploads. |
| **Question Detection & Extraction** | Regex & heuristic parser for numbered questions & headings | `app/services/extraction/parser.py`<br>`app/services/extraction/models.py` | `tests/unit/test_extraction_unit.py`<br>`tests/test_question_extraction.py` | **Complete** | Classifies MCQ, True/False, Numerical, Short Answer, Long Answer; filters exam boilerplate headers. |
| **MCQ Options Extraction** | Multi-pattern option extractor (vertical lists & inline) | `app/services/extraction/parser.py` | `tests/unit/test_extraction_unit.py` | **Complete** | Detects labels `(A)-(D)`, `A.-D.`, `A)-D)`; preserves order and text content. |
| **Multi-Page Question Continuation** | Cross-page boundary stitching logic | `app/services/extraction/parser.py`<br>`app/services/document_processor.py` | `tests/unit/test_extraction_unit.py`<br>`tests/test_question_extraction.py` | **Complete** | Unbroken questions spanning page breaks stitched with preserved source page references. |
| **Source Page & Bounding Box Traceability** | Page-number tracking & bounding box coordinates | `app/db/models/question.py`<br>`app/schemas/question.py` | `tests/test_question_extraction.py` | **Complete** | Source page IDs and normalized geometry stored per question for visual UI highlighting. |
| **Answer Key Extraction & Normalization** | Text & table answer schedule parser | `app/services/answer_extraction/answer_key_service.py` | `tests/unit/test_answer_mapping_unit.py`<br>`tests/test_answer_extraction.py` | **Complete** | Parses inline (`1. A, 2. B`) and tabular schedules; handles uncertainty tokens (`?`, `unclear`). |
| **Answer Association & Question Linking** | Deterministic number & label matcher | `app/services/answer_extraction/answer_matcher.py` | `tests/unit/test_answer_mapping_unit.py`<br>`tests/test_answer_extraction.py` | **Complete** | Maps answers to questions; flags ambiguity or unmapped questions without ungrounded guessing. |
| **Document Relationship Management** | Parent-child linking (`QUESTION_PAPER` $\leftrightarrow$ `ANSWER_KEY`) | `app/db/models/related_document.py`<br>`app/api/v1/documents.py` | `tests/integration/test_api_lifecycle.py` | **Complete** | Dedicated `/documents/{id}/related` endpoint links answer key to question paper and triggers re-matching. |
| **Confidence Scoring Engine** | Weighted composite score over 8 independent signals | `app/services/confidence/confidence_engine.py`<br>`app/services/confidence/confidence_signals.py` | `tests/unit/test_confidence_unit.py`<br>`tests/test_confidence_and_review.py` | **Complete** | Weights sum to 1.0; evaluates OCR quality, text density, boundary clarity, options, and answer match. |
| **Human Review Workflow** | Review item generation, severity ranking, and resolution | `app/services/confidence/review_service.py`<br>`app/api/v1/reviews.py` | `tests/unit/test_review_unit.py`<br>`tests/test_confidence_and_review.py` | **Complete** | Auto-flags `LOW_CONFIDENCE`, `MISSING_OPTIONS`, `AMBIGUOUS_ANSWER`; supports `OPEN` $\to$ `RESOLVED`/`IGNORED`. |
| **Standardized Error Handling** | Global exception handlers with structured envelope | `app/core/exceptions.py` | `tests/test_auth.py`<br>`tests/test_documents.py` | **Complete** | Uniform `{ "error": { "code": "...", "message": "...", "details": ... } }` response structure. |
| **Pagination & Filtering** | Standardized pagination metadata & field filters | `app/schemas/document.py`<br>`app/schemas/question.py`<br>`app/api/v1/documents.py` | `tests/test_documents.py`<br>`tests/integration/test_api_lifecycle.py` | **Complete** | `page`, `page_size`, `total_pages`, `total` returned with filters (`status`, `question_type`, `review_required`). |
| **Automated Testing Suite** | Unit, integration, authorization, concurrency, error tests | `tests/conftest.py`<br>`tests/unit/`<br>`tests/integration/` | `.venv/bin/pytest` (134 passing tests) | **Complete** | 100% test execution pass rate in under 8 seconds with zero external dependencies. |
| **Postman API Collection** | Exported v2.1.0 collection with auto-chaining tests | `postman/Document-Intelligence-Service.postman_collection.json` | Postman Runner | **Complete** | End-to-end chained calls with bearer token & ID automation. |
| **Evaluator Documentation** | Architecture, Security, Pipeline, Demo, Quickstart guides | `README.md`<br>`docs/*.md` | Document review | **Complete** | 8 dedicated guide documents and complete project README. |

---

## Requirement Fulfillment Summary

- **Total Assessed Requirements**: 23
- **Complete**: 23 (100%)
- **Partial**: 0 (0%)
- **Missing / Gaps**: 0 (0%)
