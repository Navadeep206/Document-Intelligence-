# Document Intelligence & Question Extraction Service

An enterprise-grade, asynchronous document ingestion and intelligence service engineered to extract structured questions, multiple-choice options, source page provenance, and answer associations from digital and scanned examination papers.

---

## 1. Overview

The **Document Intelligence & Question Extraction Service** is an end-to-end backend platform designed for academic institutions, assessment platforms, and educational organizations. It ingests examination papers in PDF, JPG, and PNG formats, automatically distinguishes digital text from scanned images, applies optical character recognition (OCR) where necessary, segments questions across page boundaries, associates official answer keys, computes confidence scores, and routes uncertain extractions to an actionable human review workflow.

---

## 2. Problem Statement

Educational institutions and assessment providers frequently manage examination papers stored as unstructured PDFs or degraded paper scans. Processing these documents manually is labor-intensive, error-prone, and slow. Existing automated solutions often suffer from critical shortcomings:
1. **Accidental Boundary Merging**: Questions sharing a single page or questions spanning page boundaries are improperly merged or truncated.
2. **Silent Hallucinations**: Semantic matching systems often guess answers when references are missing or ambiguous.
3. **Black-Box Failures**: Lack of source-page traceability makes visual verification impossible.
4. **Synchronous Bottlenecks**: Heavy PDF processing and OCR cause HTTP gateway timeouts.

This service solves these challenges with an asynchronous pipeline combining native PDF parsing, OCR fallback, deterministic answer association, multi-signal confidence scoring, and multi-tenant security.

---

## 3. Features

* **Multi-Format Ingestion**: Supports digital PDFs, scanned PDFs, JPEG, and PNG images up to 25 MB.
* **Dual-Engine Text Extraction**: Instantaneous native PDF text extraction via PyMuPDF (`fitz`) with automatic fallback to Tesseract OCR when native text is sparse (<20 characters) or absent.
* **Structured Question Segmentation**: Detects multiple question types: Multiple Choice Questions (MCQ), True/False, Numerical, Short Answer, and Long Answer.
* **Option & Layout Parsing**: Segments vertical lists and inline MCQ options `(A)-(D)`, preserving option labels, text, and positional order.
* **Multi-Page Continuity**: Cross-page boundary stitching logic preserves questions spanning across page breaks.
* **Answer-Key Intelligence**: Ingests answer schedules (inline and tabular grid formats), normalizing references and matching answers to questions with zero silent guessing.
* **Multi-Signal Confidence Engine**: Evaluates 8 weighted signals (OCR confidence, text density, boundary clarity, options presence, answer match) into a normalized score ($0.0 - 1.0$).
* **Human Review Queue**: Automatically diverts low-confidence or structurally ambiguous questions to a review queue with actionable severity levels and resolution endpoints.
* **Security & Multi-Tenancy**: Secure password hashing with Argon2id, RFC-7519 JWT bearer authentication, and strict multi-tenant database isolation.
* **Source Provenance & Bounding Boxes**: Retains source page numbers and normalized bounding box coordinates for visual auditability.

---

## 4. Architecture

The service adopts a decoupled, event-driven microservices architecture:

```mermaid
flowchart TD
    Client["Client / Evaluator / Browser"] --> API["FastAPI Application Gateway (Port 8000)"]

    subgraph Core_Services ["FastAPI Core Services"]
        API --> Auth["Authentication & Authorization (Argon2id + JWT)"]
        API --> Validator["Upload Validator (Magic Bytes & MIME)"]
        API --> Storage["Storage Service (Local Driver / Abstraction)"]
    end

    API --> DB[("PostgreSQL 16 (Relational Metadata & Audit Store)")]
    API --> Queue[("Redis 7 (Broker & Distributed State)")]

    Queue --> Worker["Celery Distributed Worker Farm"]

    subgraph Processing_Pipeline ["Asynchronous Processing Pipeline"]
        Worker --> StorageRead["Retrieve Document from Storage"]
        StorageRead --> Pages["PDF/Image Processing (PyMuPDF)"]
        Pages --> OCR["OCR / Text Extraction (Tesseract Engine)"]
        OCR --> Questions["Question Detection & Extraction (MCQ, T/F, Descr)"]
        Questions --> Answers["Answer-Key Intelligence & Association"]
        Answers --> Confidence["Confidence Engine (8 Multi-Signal Scoring)"]
        Confidence --> Review["Human Review Manager (Flagging & Deduplication)"]
    end

    Questions --> DB
    Answers --> DB
    Confidence --> DB
    Review --> DB
```

Detailed architectural specifications and diagrams are available in [docs/architecture.md](file:///Users/navadeepguduru/PNBC/document-intelligence-service/docs/architecture.md).

---

## 5. Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **API Framework** | FastAPI (v0.115) | Asynchronous ASGI Web framework & OpenAPI documentation |
| **Language** | Python 3.12 | Core programming runtime |
| **Database** | PostgreSQL 16 | Relational persistence, constraints & multi-tenant isolation |
| **ORM** | SQLAlchemy 2.0 | Type-annotated relational mapping & queries |
| **Migrations** | Alembic 1.14 | Managed database schema revisions |
| **Queue / Broker** | Redis 7 | High-performance in-memory message broker & cache |
| **Async Worker** | Celery 5.4 | Distributed background task execution & retry logic |
| **OCR Engine** | Tesseract 5 / pytesseract | Optical character recognition for scanned pages & images |
| **PDF Processing** | PyMuPDF (fitz 1.24) | High-speed PDF rendering, text extraction, page splitting |
| **Validation** | Pydantic v2 | Strict request/response schema modeling & sanitization |
| **Authentication** | PyJWT | Cryptographically signed HMAC-SHA256 bearer tokens |
| **Password Hashing** | Argon2id (`argon2-cffi`) | Memory-hard password hashing competition standard |
| **Testing** | Pytest 8.4 | Hermetic unit, integration, and security testing |
| **Documentation** | OpenAPI 3.0 / Swagger | Interactive live API documentation & exploration |
| **Deployment** | Docker & Docker Compose | Containerized service orchestration with health checks |

---

## 6. Processing Pipeline

```mermaid
flowchart LR
    Upload["1. Secure Upload"] --> Validate["2. Validate Magic Bytes"]
    Validate --> Store["3. Store Disk ({uuid}.ext)"]
    Store --> Queue["4. Enqueue Celery Task"]
    Queue --> ExtractPages["5. Render / Extract Pages"]
    ExtractPages --> OCR{"6. Native Text >= 20 chars?"}
    OCR -- Yes --> DetectQuestions["7. Detect Questions"]
    OCR -- No (Scanned/Image) --> RunOCR["Run Tesseract OCR"] --> DetectQuestions
    DetectQuestions --> Structure["8. Parse Options & Boundaries"]
    Structure --> AnswerMapping["9. Associate Answer Key"]
    AnswerMapping --> Confidence["10. Score Confidence (8 Signals)"]
    Confidence --> Review{"11. Score < 0.85 or Issues?"}
    Review -- Yes --> FlagReview["Create Review Items"] --> Complete["12. COMPLETED"]
    Review -- No --> Complete
```

1. **Upload & Ingestion**: Validates file extension, MIME type, and magic bytes (`%PDF-`, `\x89PNG`, `\xff\xd8\xff`). Stores with randomized UUID filename.
2. **Page Ingestion**: Deconstructs document into discrete `document_pages` with sequence ordering.
3. **Text Extraction**: Attempts native PyMuPDF digital text extraction. If text is sparse (<20 characters), renders image at 250 DPI and invokes Tesseract OCR with Otsu preprocessing.
4. **Question Detection**: Parses question numbers (`1.`, `Q2:`, `(3)`), classifies question types, and strips boilerplate header/footer text.
5. **Option Extraction**: Parses vertical and inline option patterns `(A)-(D)`, preserving option labels and order.
6. **Multi-Page Stitching**: Detects questions spanning page breaks and merges them while tracking multiple source page IDs.
7. **Answer Mapping**: Resolves answer keys against question numbers with explicit ambiguity detection.
8. **Confidence Scoring & Review**: Multi-signal scoring engine computes question confidence and generates review items where warranted.

Further pipeline details: [docs/extraction-pipeline.md](file:///Users/navadeepguduru/PNBC/document-intelligence-service/docs/extraction-pipeline.md).

---

## 7. Data Model

The relational data model comprises 11 normalized PostgreSQL tables:

```mermaid
erDiagram
    USERS ||--o{ DOCUMENTS : owns
    DOCUMENTS ||--o{ DOCUMENT_PAGES : contains
    DOCUMENTS ||--o{ PROCESSING_JOBS : tracks
    DOCUMENTS ||--o{ QUESTIONS : extracts
    DOCUMENTS ||--o{ ANSWER_KEYS : defines
    DOCUMENTS ||--o{ ANSWER_MAPPINGS : maps
    DOCUMENTS ||--o{ REVIEW_ITEMS : flags
    DOCUMENTS ||--o{ RELATED_DOCUMENTS : links

    QUESTIONS ||--o{ QUESTION_OPTIONS : has
    QUESTIONS ||--o{ QUESTION_SOURCES : references
    QUESTIONS ||--o{ REVIEW_ITEMS : triggers
    QUESTIONS ||--o| ANSWER_MAPPINGS : resolves

    DOCUMENT_PAGES ||--o{ QUESTION_SOURCES : locates
    ANSWER_KEYS ||--o{ ANSWER_MAPPINGS : associates
```

* **`users`**: Authentication credentials, Argon2id password hash, tenant scope.
* **`documents`**: Document metadata, storage path, status (`PROCESSING`, `COMPLETED`, `FAILED`), role (`QUESTION_PAPER`, `ANSWER_KEY`).
* **`document_pages`**: Page numbers, extracted text, OCR indicator, confidence scores.
* **`processing_jobs`**: Celery task tracking, retry counts, timing telemetry, error logs.
* **`questions`**: Extracted questions, classifications, confidence scores, review flags.
* **`question_options`**: Options for MCQs (`A`, `B`, `C`, `D`), text content, positional index.
* **`question_sources`**: Multi-page links and bounding box coordinates (`x`, `y`, `width`, `height`).
* **`answer_keys`**: Raw and structured answer schedules.
* **`answer_mappings`**: Associations between questions and answers with match status (`MATCHED`, `UNMATCHED`).
* **`related_documents`**: Bidirectional links between question papers and answer key documents.
* **`review_items`**: Human review queue items with status (`OPEN`, `RESOLVED`, `IGNORED`) and severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).

---

## 8. Confidence & Human Review

Every question receives a composite score calculated from 8 normalized weights summing to 1.0:

$$\text{Confidence} = \sum_{i=1}^{8} (w_i \times s_i)$$

* **OCR Confidence Signal** ($w=0.20$): Character and word recognition reliability from Tesseract.
* **Text Density & Length Signal** ($w=0.20$): Verifies sufficient question body text.
* **Boundary Clarity Signal** ($w=0.15$): Validates clear demarcation between successive questions.
* **Option Extraction Signal** ($w=0.10$): Verifies MCQ options contain $\ge 2$ detected choices.
* **Numbering Integrity Signal** ($w=0.10$): Verifies sequential question numbering.
* **Answer Mapping Signal** ($w=0.10$): Verifies unambiguous answer association.
* **Source Traceability Signal** ($w=0.10$): Confirms valid page mapping and bounding box coordinates.
* **Page Quality Signal** ($w=0.05$): Penalizes skew and noise.

### Thresholds & Review Lifecycle
* **$\text{Confidence} \ge 0.85$**: Status `EXTRACTED`, review not required.
* **$0.60 \le \text{Confidence} < 0.85$**: Status `REVIEW_REQUIRED`, severity `MEDIUM`.
* **$\text{Confidence} < 0.60$**: Status `REVIEW_REQUIRED`, severity `HIGH`.
* **Structural Anomalies**: MCQ with $<2$ options triggers `INCOMPLETE_OPTIONS`; conflicting answers trigger `AMBIGUOUS_ANSWER`.

Evaluators and operators can resolve review items via `PATCH /api/v1/reviews/{id}` with resolution notes.

---

## 9. Security

* **Password Security**: Argon2id (`m=65536, t=3, p=4`) with constant-time verification against timing attacks.
* **Token Authentication**: Signed HMAC-SHA256 JWT tokens with 30-minute expiry.
* **Multi-Tenant Isolation**: All queries enforce `user_id` ownership constraints. Non-owned resources return uniform `404 Not Found` responses to prevent user enumeration.
* **File Upload Protections**: Enforces magic-byte verification (`%PDF-`, `\x89PNG`, `\xff\xd8\xff`), MIME type whitelisting, and strict 25 MB streaming limits.
* **Path Traversal Guards**: Uploads are saved using randomized UUID filenames (`{uuid4}.{ext}`) in an isolated directory outside the Python package.
* **No Secrets Committed**: All secrets are parameterized via environment variables with safe development defaults.

Full security documentation: [docs/security.md](file:///Users/navadeepguduru/PNBC/document-intelligence-service/docs/security.md).

---

## 10. API Overview

All routes are versioned under `/api/v1` and return standardized responses:

* **Auth**:
  * `POST /api/v1/auth/register` — User registration
  * `POST /api/v1/auth/login` — JWT token acquisition
  * `GET /api/v1/auth/me` — Current user profile
* **Documents**:
  * `POST /api/v1/documents/upload` — Multipart document upload (HTTP 202)
  * `GET /api/v1/documents` — Paginated list of user documents
  * `GET /api/v1/documents/{id}` — Document metadata and counts
  * `GET /api/v1/documents/{id}/status` — Real-time processing telemetry
* **Questions**:
  * `GET /api/v1/documents/{id}/questions` — Filtered & paginated extracted questions
  * `GET /api/v1/questions/{id}` — Question details, options & bounding boxes
* **Answers & Relationships**:
  * `GET /api/v1/documents/{id}/answer-key` — Extracted answer schedule
  * `POST /api/v1/documents/{id}/related` — Link question paper to answer key
  * `GET /api/v1/documents/{id}/answer-mappings` — Answer associations
* **Human Review**:
  * `GET /api/v1/documents/{id}/reviews` — Review queue for document
  * `PATCH /api/v1/reviews/{id}` — Resolve review item (`OPEN` $\to$ `RESOLVED`)
* **Health**:
  * `GET /health` & `GET /health/ready` — Liveness and readiness probes

Full API reference: [docs/api.md](file:///Users/navadeepguduru/PNBC/document-intelligence-service/docs/api.md).

---

## 11. Local Setup

### Prerequisites
* **Docker & Docker Compose** (Recommended) — OR —
* Python 3.12+, PostgreSQL 16, Redis 7, and Tesseract OCR installed locally.

### Environment Configuration
Copy the configuration template:
```bash
cp .env.example .env
```

---

## 12. Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/document_intelligence` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis base URL |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Celery task broker queue |
| `CELERY_RESULT_BACKEND`| `redis://localhost:6379/2` | Celery task result backend |
| `JWT_SECRET_KEY` | `change-this-in-production...` | Secret key for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT signature algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifespan |
| `MAX_UPLOAD_SIZE_MB` | `25` | Maximum upload file size limit |
| `UPLOAD_DIR` | `./storage/uploads` | Path to upload directory |
| `TESSERACT_CMD` | `tesseract` | System path to Tesseract binary |
| `OCR_DPI` | `250` | Render DPI for OCR image processing |
| `MIN_NATIVE_TEXT_CHARS`| `20` | Character threshold for OCR fallback |

---

## 13. Running the Application

### Option A: Via Docker Compose (Recommended)
```bash
docker compose up --build -d
```
All containers (`api`, `worker`, `postgres`, `redis`) start automatically with volume mounts and health checks.

### Option B: Local Python Runtime
```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI documentation is live at:
* **Swagger UI**: `http://localhost:8000/docs`
* **ReDoc**: `http://localhost:8000/redoc`

---

## 14. Running Celery

If running locally without Docker:
```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```
The Celery worker connects to Redis, receives `process_document` tasks, and coordinates the ingestion, OCR, extraction, and confidence scoring pipeline.

---

## 15. Running Tests

The test suite is fully hermetic and requires zero running external services (using SQLite in-memory and task mocking):

```bash
pytest -v
```

**Verified Test Results**:
```text
============================= test session starts ==============================
collected 134 items

tests/integration/test_api_lifecycle.py .                                [  0%]
tests/integration/test_authorization_matrix.py .                         [  1%]
tests/integration/test_concurrency.py .                                  [  2%]
tests/integration/test_idempotency.py .                                  [  2%]
tests/integration/test_processing_failure.py .                           [  3%]
tests/test_answer_extraction.py ..........                               [ 11%]
tests/test_auth.py .........                                             [ 17%]
tests/test_confidence_and_review.py ..........                           [ 25%]
tests/test_documents.py ............                                     [ 34%]
tests/test_health.py ......                                              [ 38%]
tests/test_models.py .........                                           [ 45%]
tests/test_page_processing.py ..............                             [ 55%]
tests/test_pipeline.py ........                                          [ 61%]
tests/test_question_extraction.py .............                          [ 71%]
tests/unit/test_answer_mapping_unit.py .........                         [ 78%]
tests/unit/test_confidence_unit.py .....                                 [ 82%]
tests/unit/test_extraction_unit.py ...........                           [ 90%]
tests/unit/test_file_validation.py ..........                            [ 97%]
tests/unit/test_review_unit.py ...                                       [100%]

============================= 134 passed in 7.49s ==============================
```

---

## 16. Demo Walkthrough

A pre-packaged, deterministic evaluator demo is ready in `samples/demo/`:

1. **Register/Login**: Acquire JWT token via `POST /api/v1/auth/login`.
2. **Upload Exam**: Upload `samples/demo/digital_exam.pdf`.
3. **Poll Status**: Call `GET /api/v1/documents/{id}/status` until `COMPLETED`.
4. **Inspect Questions**: Call `GET /api/v1/documents/{id}/questions` to view structured MCQs and options.
5. **Associate Answer Key**: Upload `samples/demo/answer_key.pdf`, link via `POST /api/v1/documents/{id}/related`, and view `GET /api/v1/documents/{id}/answer-mappings`.
6. **Trigger Review**: Upload `samples/demo/low_quality_exam.pdf` to observe reduced confidence scores and inspect review items via `GET /api/v1/documents/{id}/reviews`.
7. **Resolve Item**: Resolve via `PATCH /api/v1/reviews/{id}` with resolution notes.

* Walkthrough Guide: [docs/demo.md](file:///Users/navadeepguduru/PNBC/document-intelligence-service/docs/demo.md)
* Copy-Paste cURL Commands: [docs/demo-commands.md](file:///Users/navadeepguduru/PNBC/document-intelligence-service/docs/demo-commands.md)
* Evaluator 3-Minute Quickstart: [docs/evaluator-quickstart.md](file:///Users/navadeepguduru/PNBC/document-intelligence-service/docs/evaluator-quickstart.md)

---

## 17. Sample Output

Generated output from the real extraction pipeline is saved in:
* [samples/output/final-example.json](file:///Users/navadeepguduru/PNBC/document-intelligence-service/samples/output/final-example.json) — Complete structured questions with options, answers, confidence scores, and source pages.
* [samples/output/review-example.json](file:///Users/navadeepguduru/PNBC/document-intelligence-service/samples/output/review-example.json) — Structured question requiring human review with open review items and severity indicators.

---

## 18. Design Trade-Offs

Detailed architectural trade-offs are documented in [docs/tradeoffs.md](file:///Users/navadeepguduru/PNBC/document-intelligence-service/docs/tradeoffs.md):
* **FastAPI vs. Django / Flask**: High-speed asynchronous I/O and automatic OpenAPI schemas over heavy monolithic frameworks.
* **PostgreSQL vs. Document Stores**: Strict relational normalization, foreign key cascades, and ACID transactions over unstructured JSON trees.
* **Celery + Redis vs. Synchronous Execution**: Predictable HTTP response times (<50ms) and horizontal worker scaling over request blocking.
* **Tesseract vs. Cloud Vision APIs**: Data privacy, zero per-page billing, and offline local evaluation over vendor lock-in.
* **Deterministic Matching vs. LLM Hallucinations**: Zero false-positive guesses and auditability over unverified semantic guessing.

---

## 19. Limitations

* **Scan Contrast Sensitivity**: Tesseract OCR performance depends on DPI resolution ($\ge 200$ DPI recommended) and physical scan contrast.
* **Complex Multi-Column Tables & Vector Diagrams**: Complex nested tabular grids and non-text diagrams are captured as visual references rather than converted into symbolic formulas.
* **Heuristic Layout Dependency**: Highly irregular or artistic fonts may lower confidence scores, intentionally redirecting to human review.
* **Storage Provider**: The default storage driver targets the local filesystem. Production cloud deployments should enable the S3 driver.

---

## 20. Future Improvements

* **S3 / Cloud Storage Adapter**: Drop-in S3 / MinIO storage driver implementation for multi-node deployments.
* **Distributed GPU OCR Nodes**: Dedicated Celery queues with GPU acceleration for high-volume OCR workloads.
* **LayoutLM / Deep Learning Segmentation**: Vision-language models for advanced multi-column newspaper layouts.
* **Interactive Human Review Web UI**: Visual split-screen review dashboard displaying original PDF pages side-by-side with extracted questions.
* **Document Versioning**: Track question edits and extraction iterations with audit history.
