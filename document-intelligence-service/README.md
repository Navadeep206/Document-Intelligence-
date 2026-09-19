# Document Intelligence & Question Extraction Service

Production-oriented backend platform engineered for scalable, automated processing of examination papers, question banks, and answer keys from scanned and digital documents (PDF, JPG, JPEG, PNG).

---

## 📌 Current Phase: Phase 8 (Confidence Engine & Human Review System)

> **Scope Status**:
> * **Phase 1**: Completed. Architectural foundation, FastAPI app, Redis, Celery worker framework, structured logging, global error handling, and health probes.
> * **Phase 2**: Completed. Production PostgreSQL data model with 11 domain entities, 10 enums, UUID primary keys, check constraints, cascade policies, and reversible Alembic migrations.
> * **Phase 3**: Completed. Argon2id password hashing, JWT authentication, current-user dependency, local storage abstraction, upload validation (extension, MIME, magic bytes, size limit), ownership-restricted document CRUD, and protected file streaming.
> * **Phase 4**: Completed. Upload-to-Celery orchestration returning HTTP 202 Accepted, ProcessingJob lifecycle tracking (`PENDING` -> `RUNNING` -> `COMPLETED` / `FAILED`), Document status transitions (`QUEUED` -> `PROCESSING` -> `COMPLETED` / `FAILED`), controlled exponential backoff retries, fail-fast permanent error handling, task idempotency guards, and real-time processing status polling API.
> * **Phase 5**: Completed. Document structural inspection (PyMuPDF / Pillow), digital text extraction, empty/low-text heuristic detection, high-resolution page rendering (250 DPI), image preprocessing (orientation transpose, grayscale, contrast enhancement), Tesseract OCR fallback with word-level confidence aggregation (0.0–1.0), non-destructive text normalization, page-by-page database persistence in `DocumentPage`, partial processing fault tolerance, and `GET /api/v1/documents/{id}/pages` API.
> * **Phase 6**: Completed. Structured question detection and extraction transforming `DocumentPage.text_content` into relational `Question`, `QuestionOption`, and `QuestionSource` entities. Supports scoring-based boundary detection across diverse numbering formats, multi-format option parsing, deterministic `QuestionType` classification, multi-page question continuation tracking, transactional delete-and-rebuild idempotency, and `GET /api/v1/documents/{document_id}/questions` API.
> * **Phase 7**: Completed. Deterministic answer-key detection, multi-format answer entry parsing (`1. A`, `1) B`, `1 - C`, `1: D`, True/False, numerical, multi-answers, single-line multi-column grids), provenance-tracked question-answer association, strict "No Silent Guessing" policy, same-document and separate-document answer-key workflows, `POST / GET /documents/{id}/related`, `GET /documents/{id}/answers`, `GET /documents/{id}/answer-key`, and `GET /questions/{id}` APIs.
> * **Phase 8**: Completed. Production confidence scoring engine & human review system. Explainable, multi-factor confidence evaluation (OCR quality, text quality, boundary certainty, question numbering, MCQ option completeness, source traceability, multi-page continuity, answer mapping), automatic question status classification (`EXTRACTED`, `PARTIAL`, `REVIEW_REQUIRED`), actionable review item generation with machine-readable reasons and severities (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), idempotent deduplication preserving human decisions, document review telemetry summary, and review management APIs (`GET /documents/{id}/reviews`, `GET /documents/{id}/reviews/summary`, `GET /questions/{id}/reviews`, `PATCH /reviews/{id}`).
> * **Phases 9–10**: Full-text / faceted question search, review dashboard frontend, and production hardening.

---

## 🏗️ Architecture Overview

The platform decouples synchronous API traffic from compute-intensive extraction tasks using an asynchronous worker queue:

```
Client (Web / Mobile / API Consumer)
  │
  ├──► 1. POST /api/v1/documents (File + Role)
  │     ├── JWT Authentication & Ownership Check
  │     ├── File Type, Signature, and Size Validation
  │     ├── Storage Persistence ({uuid4}.ext)
  │     ├── PostgreSQL: Document (QUEUED) + ProcessingJob (PENDING)
  │     ├── Redis Broker: Celery Task Enqueued (delay)
  │     └── HTTP 202 Accepted {id, job_id, status: QUEUED}
  │
  ├──► 2. Asynchronous Celery Worker Farm
  │     ├── Task: document_processing.process_document
  │     ├── DocumentInspector: Validate integrity & count pages
  │     ├── Page Ingestion Loop (Native Digital Text or Tesseract OCR @ 250 DPI)
  │     ├── Persistence: DocumentPage(document_id, page_number, ...)
  │     ├── Phase 6 Question Extraction Engine (filters answer-key sections)
  │     ├── Phase 7 Answer Extraction & Association Engine:
  │     │     ├── AnswerKeyDetector: Section/page boundary detection & negative filters
  │     │     ├── AnswerParser: Multi-format entry extraction (standard, grid, T/F, numerical)
  │     │     ├── AnswerMatcher: Strict deterministic question mapping (no silent guessing)
  │     │     └── Persistence: AnswerKey & AnswerMapping + Question.answer updates
  │     ├── Phase 8 Confidence Engine & Review System:
  │     │     ├── SignalEvaluator: 8 measurable signals (OCR, text, boundary, numbering, options, source, continuity, answers)
  │     │     ├── ConfidenceEngine: Weighted score calculation + question status classification (EXTRACTED, PARTIAL, REVIEW_REQUIRED)
  │     │     └── ReviewService: Idempotent ReviewItem sync, pruning, and document summary telemetry
  │     └── Final Status: COMPLETED, PARTIAL, or FAILED
  │
  ├──► 3. GET /api/v1/documents/{document_id}/status (Real-time job & page_count)
  ├──► 4. GET /api/v1/documents/{document_id}/pages (Extracted page text & OCR metadata)
  ├──► 5. GET /api/v1/documents/{document_id}/questions (Extracted questions, options, answers, & review flags)
  ├──► 6. GET /api/v1/documents/{document_id}/answers (Answer key & associated mappings)
  ├──► 7. POST /api/v1/documents/{document_id}/related (Establish cross-document relationships)
  ├──► 8. GET /api/v1/questions/{question_id} (Detailed question with options, answer, and review items)
  ├──► 9. GET /api/v1/documents/{document_id}/reviews (Document-wide review items with filters)
  ├──► 10. GET /api/v1/documents/{document_id}/reviews/summary (Review item telemetry & counts)
  ├──► 11. GET /api/v1/questions/{question_id}/reviews (Question-level review items)
  └──► 12. PATCH /api/v1/reviews/{review_id} (Human reviewer resolution & note updates)
```

For complete architectural details, see [docs/architecture.md](docs/architecture.md).

---

## 🧠 Question Detection & Structured Extraction Pipeline (Phase 6)

### 1. Scoring-Based Boundary Detection
* Supports explicit prefixes (`Q1.`, `Q.1`, `Question 1:`, `Question No. 1`).
* Supports standard numeric patterns (`1.`, `1)`, `1:`, `1 -`, `01.`, `12)`).
* Supports standard Roman numerals (`I.`, `II.`, `III.`, `IV.`, `(I)`, `(II)`).
* Supports unnumbered interrogatives (`Which of the following... ?`).
* Applies negative heuristics to discard exam section headings (`SECTION A`, `PART 1`, `Instructions: ...`, `Page 1 of 5`).

### 2. Contextual Option Parsing
* Handles standard lettered choices (`A.`, `A)`, `(A)`, `[A]`, `a.`, `a)`).
* Handles numeric choice options (`(1)`, `(2)`, `(3)`, `(4)`).
* Detects and splits horizontal multi-column options on a single line (`(A) Stack   (B) Queue   (C) Tree   (D) Graph`).
* Isolates clean question stem by cleanly stripping options and formatting.
* Enforces uppercase normalized labels (`A`, `B`, `C`, `D`) and 1-indexed sequential positions.

### 3. Deterministic Question Type Classification
* `MCQ`: Questions with 2 or more extracted choices.
* `TRUE_FALSE`: Questions with True/False options or explicit "true or false" phrasing.
* `NUMERICAL`: Computational questions without options ("calculate", "evaluate", "solve", "find the value").
* `SHORT_ANSWER`: Definition questions ("define", "what is", "state").
* `LONG_ANSWER`: Descriptive questions ("explain", "describe", "discuss", "derive").
* `UNKNOWN`: Default fallback for ambiguous structures.

### 4. Multi-Page Continuity & Traceability
* Questions starting on Page $K$ and concluding on Page $K+1$ are preserved as a single coherent `Question`.
* Relational `QuestionSource` table records each contributing page with ordered `page_sequence` values.

---

## 🎯 Confidence Engine & Human Review System (Phase 8)

### 1. Multi-Factor Explainable Scoring
Confidence is computed on a continuous $0.0 \dots 1.0$ scale via a deterministic weighted combination of 8 measurable signals:
* **OCR Quality (15%)**: Aggregated word confidence from Tesseract OCR or perfect score ($1.0$) for digital PDF extraction. Deductions applied for excessive non-ASCII/garbage characters.
* **Question Text Quality (15%)**: Evaluates length adequacy, word count, terminal punctuation (`?`, `.`), capitalization, and structural integrity.
* **Boundary Certainty (15%)**: Evaluates unambiguous boundary markers (`Q1.`, `Question 1:`, Roman numerals, numbered items) and pattern consistency.
* **Question Numbering (10%)**: Validates detection of explicit, well-formed question numbers (`1`, `2`, `Q1`, `iv`).
* **MCQ Option Completeness (15%)**: Validates option count (e.g. 4 choices), sequential labels (`A, B, C, D`), non-empty option text, and deduplication. Non-MCQs receive an exempt baseline score ($1.0$) so they are not penalized.
* **Source Traceability (10%)**: Confirms valid link to `QuestionSource` pages and presence of extracted page text.
* **Multi-Page Continuity (10%)**: Validates sequential page ordering for multi-page questions.
* **Answer Mapping (10%)**: Evaluates presence and confidence of associated answers. Documents without answer keys receive a neutral score ($0.85$) without review item creation.

### 2. Automated Question Classification
* `EXTRACTED` ($\ge 0.85$): High-confidence extraction requiring no human intervention.
* `PARTIAL` ($0.60 - 0.849$): Sub-optimal quality or minor ambiguities, usable but flagged.
* `REVIEW_REQUIRED` ($< 0.60$ or any `HIGH`/`CRITICAL` review warnings): Must be reviewed by a human annotator.

### 3. Actionable Human Review Items
Machine-readable review items are generated with standardized reason codes and severities:
* `LOW_OCR_CONFIDENCE` (MEDIUM / HIGH)
* `CORRUPTED_TEXT` (HIGH / CRITICAL)
* `AMBIGUOUS_QUESTION_BOUNDARY` (MEDIUM)
* `POSSIBLE_HEADER_OR_INSTRUCTION` (LOW)
* `MISSING_QUESTION_NUMBER` (LOW)
* `INCOMPLETE_OPTIONS` (HIGH)
* `MALFORMED_OPTIONS` (MEDIUM)
* `DUPLICATE_OPTION_LABELS` (MEDIUM)
* `MISSING_SOURCE_PAGE` (CRITICAL)
* `PAGE_GAP_DETECTED` (HIGH)
* `LOW_ANSWER_CONFIDENCE` (MEDIUM)
* `AMBIGUOUS_ANSWER_MAPPING` (HIGH)
* `MISSING_ANSWER` (LOW)
* `LOW_OVERALL_CONFIDENCE` (HIGH)

### 4. Idempotent Deduplication & Resolution Preservation
Processing reruns idempotently synchronize review items:
* Existing items matching `(question_id, reason)` are updated with latest confidence metrics.
* Reviewer decisions (`status = RESOLVED` or `IGNORED`) are strictly preserved and never overwritten by worker reruns.
* Stale open review items no longer detected after reprocessing are automatically pruned.

---

## 🔐 Authentication & Security

All document APIs require Bearer authentication. Users may only access and manage documents they own.

### 1. User Registration
* **Endpoint**: `POST /api/v1/auth/register`

### 2. User Login & Token Generation
* **Endpoint**: `POST /api/v1/auth/login`

### 3. Authenticated Profile Probe
* **Endpoint**: `GET /api/v1/auth/me`

---

## 📄 Document Management & Ingestion APIs

### 1. Upload & Enqueue Document
* **Endpoint**: `POST /api/v1/documents`
* **Status**: `202 Accepted`
* **Supported Formats**: `PDF`, `JPG`, `JPEG`, `PNG`

### 2. Poll Processing Status
* **Endpoint**: `GET /api/v1/documents/{document_id}/status`
* **Status**: `200 OK`

### 3. Retrieve Extracted Pages
* **Endpoint**: `GET /api/v1/documents/{document_id}/pages`
* **Status**: `200 OK`

### 4. Retrieve Extracted Questions (Phase 6)
* **Endpoint**: `GET /api/v1/documents/{document_id}/questions`
* **Status**: `200 OK`
* **Response** (`200 OK`):
  ```json
  {
    "document_id": "7bf3eb85-3b95-46ff-bce2-ec8bb5dbbe72",
    "total": 2,
    "items": [
      {
        "id": "2ed1b0ef-16f1-4433-8abe-6d9046113244",
        "document_id": "7bf3eb85-3b95-46ff-bce2-ec8bb5dbbe72",
        "question_number": "1",
        "question_text": "What is the fastest sorting algorithm on average?",
        "question_type": "MCQ",
        "status": "EXTRACTED",
        "confidence": 1.0,
        "answer": null,
        "answer_confidence": null,
        "answer_source": null,
        "options": [
          {"id": "cd972acb-1208-4d5f-831b-9158cce0842a", "question_id": "2ed1b0ef-16f1-4433-8abe-6d9046113244", "label": "A", "option_text": "Bubble Sort", "position": 1, "created_at": "2026-09-19T11:50:02Z"},
          {"id": "6a545501-481a-461d-8395-1a80e17d704b", "question_id": "2ed1b0ef-16f1-4433-8abe-6d9046113244", "label": "B", "option_text": "Quick Sort", "position": 2, "created_at": "2026-09-19T11:50:02Z"},
          {"id": "218e0d25-6fd1-4195-8bb2-8a3f6724cfab", "question_id": "2ed1b0ef-16f1-4433-8abe-6d9046113244", "label": "C", "option_text": "Selection Sort", "position": 3, "created_at": "2026-09-19T11:50:02Z"},
          {"id": "3bcf759a-df28-47dd-b193-db283ed45b4b", "question_id": "2ed1b0ef-16f1-4433-8abe-6d9046113244", "label": "D", "option_text": "Insertion Sort", "position": 4, "created_at": "2026-09-19T11:50:02Z"}
        ],
        "sources": [
          {"id": "676b764b-9273-4ee1-bc9a-1338f897438c", "document_page_id": "d4a1507e-16d0-4583-8b9f-c01af3cb6e46", "page_sequence": 1, "created_at": "2026-09-19T11:50:02Z"}
        ],
        "created_at": "2026-09-19T11:50:02Z",
        "updated_at": "2026-09-19T11:50:02Z"
      }
    ]
  }
  ```

### 5. List Documents (Paginated)
* **Endpoint**: `GET /api/v1/documents?page=1&page_size=20`

### 6. Retrieve Document Metadata
* **Endpoint**: `GET /api/v1/documents/{document_id}`

### 7. Download Original Document Binary
* **Endpoint**: `GET /api/v1/documents/{document_id}/file`

### 8. Delete Document
* **Endpoint**: `DELETE /api/v1/documents/{document_id}`
* **Response**: `204 No Content`. Cascades deletion to all questions, options, sources, pages, answer keys, mappings, and storage files.

### 9. Get Document Answers & Key
* **Endpoint**: `GET /api/v1/documents/{document_id}/answers`
* **Response**: `200 OK` with `AnswerListResponse` including `answer_key` metadata, total answers count, and detailed list of mapped answers (`question_id`, `question_reference`, `answer_value`, `confidence`, `source_page`).

### 10. Get Document Answer-Key Metadata
* **Endpoint**: `GET /api/v1/documents/{document_id}/answer-key`
* **Response**: `200 OK` with `AnswerKeyResponse` detailing key name, format description, and confidence score.

### 11. Connect Related Documents (e.g. Question Paper to Answer Key)
* **Endpoint**: `POST /api/v1/documents/{document_id}/related`
* **Body**: `{"related_document_id": "<uuid>", "relationship_type": "ANSWER_KEY"}`
* **Response**: `201 Created` with `RelatedDocumentResponse`. Automatically executes answer extraction and association between the documents.

### 12. List Document Relationships
* **Endpoint**: `GET /api/v1/documents/{document_id}/related`
* **Response**: `200 OK` with list of bidirectional related documents and relationship types.

### 13. Get Single Question Details
* **Endpoint**: `GET /api/v1/questions/{question_id}`
* **Response**: `200 OK` with `QuestionResponse` containing question stem, type, options, reconciled answer metadata (`answer`, `answer_confidence`, `answer_source`), and review flags (`review_required`, `review_count`).

### 14. List Document Review Items
* **Endpoint**: `GET /api/v1/documents/{document_id}/reviews?status=PENDING&severity=HIGH`
* **Response**: `200 OK` with `ReviewItemListResponse` detailing review items, question context, severity, and status.

### 15. Get Document Review Summary
* **Endpoint**: `GET /api/v1/documents/{document_id}/reviews/summary`
* **Response**: `200 OK` with `DocumentReviewSummaryResponse` (total questions, breakdown by extraction status, total review items, pending/resolved counts, and breakdown by severity and reason).

### 16. List Question Review Items
* **Endpoint**: `GET /api/v1/questions/{question_id}/reviews`
* **Response**: `200 OK` with `ReviewItemListResponse` detailing all review items for a specific question.

### 17. Update Review Item Status (Human In The Loop)
* **Endpoint**: `PATCH /api/v1/reviews/{review_id}`
* **Body**: `{"status": "RESOLVED", "notes": "Verified OCR text manually."}`
* **Response**: `200 OK` with `ReviewItemResponse` with updated status, notes, and resolution timestamp.

---

## 🚀 Tech Stack

* **Language**: Python 3.12+
* **API Framework**: FastAPI 0.115+
* **ASGI Server**: Uvicorn
* **Security & Auth**: Argon2id (`argon2-cffi`), PyJWT
* **Data Validation & Settings**: Pydantic v2 & Pydantic Settings
* **Database**: PostgreSQL 16
* **ORM & Migrations**: SQLAlchemy 2.0 & Alembic (psycopg3 driver)
* **Distributed Task Queue**: Celery 5.4+
* **Message Broker & Cache**: Redis 7
* **Containerization**: Docker & Docker Compose
* **Testing**: Pytest & HTTPX

---

## 📁 Project Structure

```
document-intelligence-service/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, lifespan, and middlewares
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py      # Aggregated v1 API router
│   │       ├── health.py        # Liveness & readiness probes
│   │       ├── auth.py          # Registration, login, and /me endpoints
│   │       └── documents.py     # Document upload, listing, download, delete
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic Settings management
│   │   ├── deps.py              # Current-user authentication dependency
│   │   ├── security.py          # Argon2id hashing and JWT token handlers
│   │   ├── logging.py           # Structured logging & request middleware
│   │   └── exceptions.py        # Centralized error response schemas & handlers
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py          # SQLAlchemy 2.x engine, sessions, & health probe
│   │   ├── base.py              # DeclarativeBase aggregating all models
│   │   └── models/              # Modular domain entities & enums
│   ├── schemas/                 # Pydantic request & response schemas
│   │   ├── __init__.py
│   │   ├── auth.py              # Registration, login, token schemas
│   │   └── document.py          # Upload, document, pagination schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── storage.py           # StorageService & LocalStorageService
│   │   └── file_validator.py    # Magic bytes, MIME, and size validation
│   └── workers/
│       ├── __init__.py
│       └── celery_app.py        # Celery app instance & baseline tasks
├── storage/
│   └── uploads/                 # Local filesystem upload root (outside app package)
├── alembic/
│   ├── versions/                # Versioned migration scripts
│   └── env.py                   # Alembic execution environment
├── tests/
│   ├── __init__.py
│   ├── test_health.py           # Pytest suite for health probes & Celery
│   ├── test_models.py           # Pytest suite for database models & constraints
│   ├── test_auth.py             # Pytest suite for registration, login, JWT
│   └── test_documents.py        # Pytest suite for upload, security, authorization
├── docs/
│   └── architecture.md          # Architectural blueprints and layer specifications
├── .env.example                 # Template environment variables
├── .gitignore                   # Version control exclusions
├── alembic.ini                  # Alembic CLI configuration
├── requirements.txt             # Pinned project dependencies
├── Dockerfile                   # Multi-stage production container image
├── docker-compose.yml           # Local multi-container orchestration
├── README.md                    # Project documentation
└── pyproject.toml               # Project metadata and tooling configuration
```

---

## 🔑 Environment Variables

```bash
cp .env.example .env
```

| Variable | Default Value | Description |
|---|---|---|
| `APP_NAME` | `document-intelligence-service` | Service identifier |
| `APP_ENV` | `development` | Deployment environment |
| `DEBUG` | `true` | Debug flag |
| `API_V1_PREFIX` | `/api/v1` | API version prefix |
| `DATABASE_URL` | `postgresql+psycopg://...` | PostgreSQL connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis instance connection string |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | Celery message broker URL |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2` | Celery task result backend URL |
| `CELERY_WORKER_CONCURRENCY` | `2` | Number of concurrent worker execution threads |
| `CELERY_TASK_MAX_RETRIES` | `3` | Maximum retry attempts for transient worker failures |
| `CELERY_TASK_RETRY_BACKOFF` | `5` | Exponential retry backoff base in seconds |
| `ALLOWED_ORIGINS` | `["http://localhost:3000"]` | CORS allowed origins |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `MAX_UPLOAD_SIZE_MB` | `25` | Maximum allowed file upload size in megabytes |
| `UPLOAD_DIR` | `/app/storage/uploads` | Absolute or relative upload directory |
| `JWT_SECRET_KEY` | *(Set in .env)* | 32+ byte cryptographic secret for token signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| `30` | Access token lifetime in minutes |
| `CONFIDENCE_WEIGHT_OCR_QUALITY` | `0.15` | Weight for OCR / digital text extraction signal |
| `CONFIDENCE_WEIGHT_QUESTION_TEXT_QUALITY` | `0.15` | Weight for stem length, punctuation, & structure signal |
| `CONFIDENCE_WEIGHT_BOUNDARY_CERTAINTY` | `0.15` | Weight for question boundary markers & separators signal |
| `CONFIDENCE_WEIGHT_QUESTION_NUMBERING` | `0.10` | Weight for valid question numbering format signal |
| `CONFIDENCE_WEIGHT_OPTION_COMPLETENESS` | `0.15` | Weight for MCQ option count, sequence, & non-emptiness |
| `CONFIDENCE_WEIGHT_SOURCE_TRACEABILITY` | `0.10` | Weight for source page presence & text linkage signal |
| `CONFIDENCE_WEIGHT_MULTI_PAGE_CONTINUITY` | `0.10` | Weight for multi-page sequence continuity signal |
| `CONFIDENCE_WEIGHT_ANSWER_MAPPING` | `0.10` | Weight for answer key association & answer confidence |
| `CONFIDENCE_THRESHOLD_EXTRACTED` | `0.85` | Score threshold for automatic high-confidence EXTRACTED status |
| `CONFIDENCE_THRESHOLD_PARTIAL` | `0.60` | Score threshold for PARTIAL status (below = REVIEW_REQUIRED) |

---

## ⚡ Starting Services Locally

```bash
# 1. Start Celery background worker
celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2

# 2. Start FastAPI development web server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🐳 Running With Docker Compose

```bash
# Build and launch all services (API, Worker, PostgreSQL, Redis)
docker compose up --build

# Stop containers
docker compose down
```

---

## 🧪 Running Tests

Execute the complete 91-test suite (health probes, models & constraints, auth & JWT, documents, asynchronous pipeline, OCR/page processing, question extraction, answer extraction, and confidence & human review engine):
```bash
pytest -v
```

---

## 🌐 Interactive API Documentation (Swagger)

* **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
* **OpenAPI Schema**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

