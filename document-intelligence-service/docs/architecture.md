# System Architecture — Document Intelligence & Question Extraction Service

## 1. Overview

The **Document Intelligence & Question Extraction Service** is an enterprise-grade, asynchronous document ingestion and intelligence platform. It is engineered to process high-volume examination papers, question banks, and answer keys in various visual and digital formats (PDF, JPG, JPEG, PNG).

* **Phase 1**: Established the foundational architecture, API gateway, Celery worker farm, containerization, and structured observability.
* **Phase 2**: Established the production-grade PostgreSQL database schema, domain models, entity relationships, integrity constraints, and Alembic migrations.
* **Phase 3**: Establishes secure authentication (Argon2id + JWT), authorization, tenant isolation, storage abstraction, upload validation, and document lifecycle APIs.

---

## 2. Conceptual End-to-End Flow

```
Client (Web / Mobile / API Consumer)
  │
  ▼
FastAPI Application Gateway (Port 8000)
  │
  ├──► JWT Authentication & Verification (Argon2id / PyJWT)
  │
  ├──► Upload Validation Pipeline
  │     ├── Extension whitelist (.pdf, .jpg, .jpeg, .png)
  │     ├── MIME type inspection
  │     ├── Magic byte integrity verification
  │     └── Chunked streaming size check (<= 25 MB)
  │
  ├──► Storage Layer (LocalStorageService / Object Storage Abstraction)
  │     └── Secure UUID naming ({uuid4}.ext) outside source package
  │
  ├──► PostgreSQL 16 (Relational Metadata & Audit Store)
  │
  └──► Redis 7 (Broker & Distributed State)
         │
         ▼
       Celery Worker Farm (Scalable Task Execution - Phases 4–10)
```

---

## 3. Database Architecture (Phase 2)

### 3.1 Entity Relationship (ER) Diagram

```
User
 │
 │ 1:N (Owner)
 ▼
Document ◄─────────────────────────────────────┐
 │                                             │
 ├──► DocumentPage (1:N)                       │
 │      ▲                                      │
 │      │ 1:N                                  │
 │   QuestionSource (N:M link)                 │
 │      │                                      │
 ├──► Question (1:N)                           │
 │      ├──► QuestionOption (1:N)              │
 │      ├──► QuestionSource (1:N)              │
 │      ├──► AnswerMapping (1:N, optional link)│
 │      └──► ReviewItem (1:N)                  │
 │                                             │
 ├──► ProcessingJob (1:N)                      │
 │                                             │
 ├──► AnswerKey (1:N)                          │
 │      └──► AnswerMapping (1:N)               │
 │                                             │
 ├──► ReviewItem (1:N)                         │
 │                                             │
 └──► RelatedDocument (Self-referential link) ──┘
```

---

## 4. Authentication, Authorization & Ingestion Architecture (Phase 3)

### 4.1 Security & Cryptography
* **Password Hashing**: Implemented via Argon2id (`argon2-cffi`), the password hashing competition winner, providing memory-hard resistance to GPU/ASIC attacks with constant-time verification.
* **Token Standard**: Cryptographically signed JSON Web Tokens (JWT) using HMAC-SHA256 (`HS256`).
* **Claims**: Standardized claims (`sub` = user UUID, `iat`, `exp`). Sensitive data and passwords are never placed inside the JWT.
* **Anti-Enumeration**: Both registration and login responses avoid leaking account existence. Non-owned document requests consistently return `404 Not Found` rather than `403 Forbidden`.

### 4.2 Storage Abstraction & Path Isolation
* **Storage Interface (`StorageService`)**:
  Defines generic persistence operations (`save`, `delete`, `exists`, `get_absolute_path`), decoupling business endpoints from filesystem particulars.
* **Security & Path Traversal Guards**:
  Original filenames are strictly separated from storage identifiers. All uploads receive randomized UUID names (`{uuid4().hex}.{ext}`) and are validated against traversal sequences (`..`, leading slashes).
* **Storage Location**:
  Configurable via `UPLOAD_DIR`. Uploaded files reside in `/app/storage/uploads` (or `./storage/uploads`), completely outside the application Python package.
* **Transaction Safety**:
  Uploads follow a write-then-commit pattern. If database persistence encounters an error, the newly written storage file is immediately deleted to eliminate orphaned files.

### 4.3 Validation Pipeline
1. **Extension Whitelist**: Permits strictly `.pdf`, `.jpg`, `.jpeg`, and `.png`. Rejects `.exe`, `.sh`, `.zip`, `.html`, etc.
2. **MIME Verification**: Matches `application/pdf`, `image/jpeg`, and `image/png`.
3. **Magic Byte Signature Inspection**: Verifies binary headers (`%PDF-`, `\x89PNG`, `\xff\xd8\xff`), rejecting renamed or corrupted files.
4. **Streaming Size Limit**: Enforces `MAX_UPLOAD_SIZE_MB` (default 25 MB) during chunked reads without exhausting server memory.

---

## 5. Asynchronous Processing Pipeline Architecture (Phase 4)

### 5.1 Architecture & Flow Diagram

```
[ Client Upload ] ──► POST /api/v1/documents
                            │
                            ├─► 1. Save file to storage/uploads/{uuid}.ext
                            ├─► 2. INSERT INTO documents (status = QUEUED)
                            ├─► 3. INSERT INTO processing_jobs (status = PENDING)
                            ├─► 4. DB COMMIT (ensures job and document exist)
                            ├─► 5. celery_app.send_task / delay()
                            │       ├── SUCCESS: UPDATE processing_jobs SET task_id = task.id; COMMIT
                            │       └── FAILURE: UPDATE job & doc SET status = FAILED; COMMIT; RAISE 503
                            └─► 6. RETURN HTTP 202 Accepted {id, job_id, status: QUEUED}

[ Celery Worker ] ──► task: document_processing.process_document(document_id, job_id)
                            │
                            ├─► A. SessionLocal DB connection established
                            ├─► B. Fetch ProcessingJob by job_id
                            ├─► C. IDEMPOTENCY CHECK: if job.status == COMPLETED -> EXIT safely
                            ├─► D. PRE-FLIGHT CHECK: if storage.exists(doc.storage_path) is False:
                            │       └── Mark job and doc FAILED (Permanent error, DO NOT RETRY)
                            ├─► E. TRANSITION: job.status = RUNNING, doc.status = PROCESSING, started_at = now()
                            ├─► F. EXECUTE: document_processor.process(...) boundary
                            ├─► G. ON SUCCESS: job.status = COMPLETED, doc.status = COMPLETED, completed_at = now()
                            └─► H. ON TRANSIENT EXCEPTION:
                                    ├── If retries < max_retries:
                                    │     countdown = base * (2 ** retries)
                                    │     raise self.retry(countdown=countdown)
                                    └── If retries exhausted:
                                          job.status = FAILED, doc.status = FAILED, completed_at = now()
```

### 5.2 Dual State Machine Mechanics

| Lifecycle Stage | `Document.status` | `ProcessingJob.status` | Description |
|---|---|---|---|
| **Accepted** | `QUEUED` | `PENDING` | Upload validated, saved to disk, committed to DB, task enqueued to Redis broker. |
| **Executing** | `PROCESSING` | `RUNNING` | Celery worker picked up task, verified file existence, stamped `started_at`. |
| **Succeeded** | `COMPLETED` | `COMPLETED` | Processing boundary completed, result recorded, stamped `completed_at`. |
| **Failed (Permanent)** | `FAILED` | `FAILED` | File missing, corrupt payload, or non-retryable error. Fails immediately without retries. |
| **Failed (Exhausted)** | `FAILED` | `FAILED` | Transient error retried `CELERY_TASK_MAX_RETRIES` (3 times with backoff 5s, 10s, 20s) and failed. |

### 5.3 Reliability & Fault Tolerance Guarantees
* **Transaction Safety on Dispatch**:
  Documents and ProcessingJobs are committed to PostgreSQL *before* Celery dispatch. If Redis broker enqueueing throws an exception, the system catches it, transitions both entities to `FAILED` with descriptive error messages, and returns `HTTP 503 Service Unavailable`, preventing records from becoming stuck in a perpetual `QUEUED` state.
* **Database as Single Source of Truth**:
  PostgreSQL retains authoritative state for all documents and processing jobs. Redis serves exclusively as a fast ephemeral broker and task transport.
* **Pre-flight Health Checks**:
  Before transitioning to `RUNNING` or running heavy processing, the worker verifies that the physical file exists on storage. Missing files cause an immediate `FAILED` transition, avoiding wasteful retry cycles.
* **Task Idempotency**:
  If a task is retried or delivered multiple times due to worker restarts (`task_acks_late=True`), the worker verifies whether `job.status == COMPLETED`. Redundant runs exit immediately without duplicating work.
* **Controlled Retry with Exponential Backoff**:
  Transient network, database, or downstream extraction exceptions trigger automatic Celery retries with `countdown = CELERY_TASK_RETRY_BACKOFF * (2 ** retries)`. After exceeding the retry budget, the job fails gracefully.

---

## 6. Document Ingestion, Page Processing & OCR Pipeline Architecture (Phase 5)

### 6.1 Ingestion Flow Diagram

```
              Document (PDF / Image)
                  │
                  ▼
             Inspection (DocumentInspector)
                  │
         ┌────────┴────────┐
         ▼                 ▼
    Digital PDF         Scan / Image
         │                 │
         ▼                 ▼
   Native Text        Render / Load
   (PyMuPDF)          (250 DPI / Pillow)
         │                 │
         │             Preprocess
         │             (Grayscale, Contrast, Exif)
         │                 │
         │                 ▼
         │                OCR (Tesseract)
         │                 │
         └────────┬────────┘
                  ▼
           Text Normalize (Strip whitespace, preserve structure)
                  │
                  ▼
            DocumentPage (PostgreSQL: text, ocr_used, ocr_confidence, rotation)
                  │
                  ▼
            Phase 6 (Question & Option Structuring)
```

### 6.2 Architectural Trade-Off: Native Digital Extraction vs. OCR
1. **Computational Efficiency & Speed**:
   Native digital PDF text extraction via PyMuPDF takes sub-millisecond CPU time per page, consuming minimal memory. In contrast, rendering high-resolution images (250 DPI) and performing neural/matrix OCR via Tesseract takes 100x–500x more compute time (~500ms to 2000ms per page).
2. **Text Fidelity & Character Accuracy**:
   Native digital text extracts exact unicode characters directly from the font glyph tables of the PDF, eliminating character recognition errors (e.g. confusing 'O' with '0', or 'l' with '1').
3. **Detection Heuristic**:
   Pages are probed with `MIN_NATIVE_TEXT_CHARS` (default: 20) and an alphanumeric density ratio (>= 25%). If the native text meets this threshold, native extraction is utilized with `ocr_used = False` and `ocr_confidence = None`. When text is absent or insufficient, the page safely falls back to raster rendering and Tesseract OCR with `ocr_used = True` and aggregated confidence.

### 6.3 Confidence Aggregation Strategy
Tesseract provides bounding box and confidence ratings on an individual word basis via `image_to_data`. To produce a trustworthy page-level telemetry value without fabricating precision:
* Non-word whitespace tokens and `-1` separator flags are pruned.
* Valid word confidence values ($conf \in [0, 100]$) are gathered.
* The arithmetic mean is computed and scaled to a normalized $[0.0, 1.0]$ float:
  $$\text{Page Confidence} = \frac{1}{N} \sum_{i=1}^N \frac{\text{conf}_i}{100.0}$$
* If no words are detected, confidence is stored as `0.0`.
* For native digital text extraction, `ocr_confidence` remains strictly `NULL` to prevent deceptive metrics.

### 6.4 Fault Tolerance & Partial Processing
Multi-page documents isolate processing per page. If an individual page fails during rendering or OCR, the error is caught and logged, a placeholder page is persisted to maintain sequential numbering, and subsequent pages continue uninterrupted. The document final status is set to `PARTIAL` rather than discarding successfully extracted pages.

---

## 7. Question Detection & Structured Extraction Architecture (Phase 6)

### 7.1 Overview
Phase 6 transforms page-level normalized text content (`DocumentPage.text_content`) into fully structured, validated relational records:
* `Question`: Question stem, numbering, classified type, extraction confidence, and lifecycle status.
* `QuestionOption`: Multi-choice options with normalized labels (`A`, `B`, `C`, `D`), clean text stripped of labels, and 1-indexed sequential positions.
* `QuestionSource`: Relational provenance tracking linking each question to the exact pages it appeared on, preserving multi-page continuity.

```
DocumentPage.text_content (Page 1..N)
             │
             ▼
Flat Sequential Line Stream (PageLine: page_num, page_id, text)
             │
             ▼
   QuestionBoundaryDetector
   ├── Prefix Matching: Q1., Q.1, Question 1:, Question No. 1
   ├── Numeric Formats: 1., 1), 1:, 1 -, 01., 12)
   ├── Roman Numerals: I., II., III., IV., (I), (II)
   ├── Unnumbered Questions (interrogatives + terminal '?')
   └── Negative Filters: Section headers, instructions, page numbers
             │
             ▼
       OptionParser
   ├── Vertical options: A., A), (A), [A], a., a), Option A:
   ├── Numeric options: (1), (2), (3), (4)
   ├── Inline horizontal multi-column options on a single line
   └── Question stem isolation (clean option stripping)
             │
             ▼
  QuestionTypeClassifier (Deterministic Classification)
   ├── MCQ (>= 2 options)
   ├── TRUE_FALSE (options True/False or explicit question phrasing)
   ├── NUMERICAL (computational interrogatives: calculate, evaluate, solve)
   ├── SHORT_ANSWER (definition and stating terms: define, what is, state)
   ├── LONG_ANSWER (descriptive analysis: explain, describe, discuss, derive)
   └── UNKNOWN (fallback)
             │
             ▼
     ExtractionValidator (Sanitization & Quality Scoring)
   ├── Minimum stem length verification
   ├── Unique option labels and sequential 1-indexing
   ├── Source page presence verification
   └── Status assignment: EXTRACTED vs. PARTIAL
             │
             ▼
Transactional Persistence (Idempotent Delete-and-Rebuild)
   ├── Delete existing questions for document (cascades to options & sources)
   ├── Never delete DocumentPage records or physical storage files
   └── Insert Question, QuestionOption, and QuestionSource records
```

### 7.2 Multi-Page Continuation & Provenance
Examination questions frequently start on one page and spill over onto the next (e.g. question stem and options A & B on Page 1, options C & D on Page 2).
The extraction engine processes document lines as a chronological stream tagged with page metadata. Question accumulation continues across page boundaries until the next question boundary or section heading is detected. When persisted, multiple `QuestionSource` records are created with ordered `page_sequence` values, guaranteeing full auditability back to each source page.

### 7.3 Transactional Idempotency
To support pipeline retries, reprocessing, and manual re-extraction without data corruption:
* Re-running extraction executes an atomic `DELETE FROM questions WHERE document_id = :id` within a database transaction.
* Cascading foreign keys remove old `question_options` and `question_sources`.
* Fresh questions, options, and sources are inserted in a single commit.
* Underlying `DocumentPage` records and storage files are never touched.

---

---

## 8. Answer-Key Detection, Extraction & Association Architecture (Phase 7)

### 8.1 Overview
Phase 7 introduces deterministic answer-key detection, multi-format answer entry parsing, and provenance-tracked question-answer association:
* **Answer-Key Detection**: Detects answer-key sections and pages within question papers and in standalone answer-key documents while rejecting exam instructions.
* **Multi-Format Parsing**: Parses diverse answer styles including standard numbering (`1. A`, `2) B`, `3 - C`), True/False, numerical, multi-answers (`A, C`), and compact single-line multi-column grids (`1. A  2. B  3. C`).
* **Deterministic Matching**: Reconciles answer references to questions using exact matches and normalized equivalents (`Q1` / `1.` -> `1`).
* **Strict "No Silent Guessing" Rule**: Ambiguous question numbers or uncertain answer entries (`?`, `unclear`) are explicitly preserved with `question_id = NULL` and lower confidence ($0.30$), rather than fabricating associations.
* **Dual Document Workflows**: Supports both same-document answer keys (appended at the back of an exam paper) and separate answer-key documents linked via `RelatedDocument`.

```
DocumentPage.text_content (or Standalone Answer Document)
                     │
                     ▼
             AnswerKeyDetector
   ├── Header Detection: ANSWER KEY, ANSWERS, SOLUTIONS, CORRECT ANSWERS
   ├── Negative Filters: "Answer all questions", "Write your answers"
   └── Section Demarcation (Page ranges, candidate lines)
                     │
                     ▼
               AnswerParser
   ├── Standard Formats: 1. A, 1) B, 1 - C, 1: D, 1 A
   ├── Grid Lines: "1. A  2. B  3. C  4. D"
   ├── True/False: 1. True, 2. False
   ├── Numerical Answers: 1. 42, 2. 3.1415
   ├── Multiple Answers: 1. A, C | 2. B/D
   └── Uncertainty Detection: Flags "?", "unclear", "none"
                     │
                     ▼
               AnswerMatcher (Zero Silent Guessing)
   ├── Normalization: Strip prefixes (Q1 -> 1, 01 -> 1)
   ├── Exact Reference Matching (candidate_count == 1) -> Confidence: 0.98
   ├── Ambiguous Numbers (candidate_count > 1) -> question_id: NULL, Confidence: 0.30
   ├── Unmatched References (candidate_count == 0) -> question_id: NULL, Confidence: 0.50
   └── Provenance Tracking: source_page on AnswerMapping
                     │
                     ▼
       AnswerExtractor (Transactional Persistence)
   ├── Atomic delete-and-rebuild for (document_id, source_document_id)
   ├── Persist AnswerKey and AnswerMapping records
   └── Update Question.answer, Question.answer_confidence, Question.answer_source
```

### 8.2 Provenance and Safe Idempotency
* **Provenance**: Every `AnswerMapping` records its originating `source_page`, preserving end-to-end lineage back to the physical page where the answer was found.
* **Idempotency**: Re-running answer extraction deletes only the `AnswerKey` and its child `AnswerMapping` records for the specific `(document_id, source_document_id)` pair, leaving questions, pages, and storage files intact.

### 8.3 Cross-Document Association via RelatedDocument
When an answer key is uploaded as a separate document:
1. Both documents are processed through the document pipeline.
2. The user establishes a relationship via `POST /api/v1/documents/{document_id}/related`.
3. The API validates user ownership for both documents and immediately triggers `answer_extractor.extract_and_associate`.
4. Extracted answers are mapped to the question paper's questions with full transactional safety.

---

---

## 9. Confidence Engine & Human Review Architecture (Phase 8)

### 9.1 Core Design Philosophy
The system does not pretend that OCR/AI extraction is always correct, nor does it silently guess when evidence is insufficient. Every extracted question receives an explainable, deterministic confidence assessment derived from observable engineering signals. Uncertainties are explicitly surfaced as actionable human review items.

### 9.2 Measurable Signal Model
Overall question confidence ($0.0 \dots 1.0$) is computed via a configurable weighted linear combination:
$$\text{Overall Confidence} = \sum_{i=1}^8 (\text{Signal}_i \times \text{Weight}_i)$$

| Signal | Default Weight | Measurable Criteria |
|---|---|---|
| **OCR Quality** | `0.20` | Native text ($1.0$), aggregated OCR word confidence ($0.0 \dots 1.0$), corruption/garbage character penalties. |
| **Question Text Quality** | `0.20` | Stem length, syntactic cohesion, absence of truncation markers (`-`, `...`), alphanumeric density. |
| **Boundary Detection** | `0.15` | Explicit prefix (`Q1.`, `Question 1:`) $\rightarrow 1.0$, numeric $\rightarrow 0.90$, unnumbered interrogative $\rightarrow 0.70$. |
| **Question Number** | `0.10` | Valid unique number ($1.0$), missing number ($0.40$), duplicate number ($0.35$). |
| **Option Completeness** | `0.10` | For MCQ: contiguous options ($1.0$), missing option (e.g. `A, B, D`) $\rightarrow 0.60$. Non-MCQs (descriptive, numerical) are not penalized ($1.0$). |
| **Source Traceability** | `0.10` | Valid link to `DocumentPage` via `QuestionSource` ($1.0$), missing sources ($0.0$). |
| **Page Continuity** | `0.05` | Single page or consecutive multi-page ($1.0$), non-consecutive page gap ($0.40$). |
| **Answer Mapping** | `0.10` | Exact match ($1.0$), no answer key present ($0.85$ neutral baseline), unmatched ($0.50$), ambiguous/conflicting ($0.30$). |

### 9.3 Status Classification & Review Thresholds
* **`EXTRACTED`**: $\ge 0.85$ (with no HIGH/CRITICAL review warnings).
* **`PARTIAL`**: $0.60 \le \text{score} < 0.85$.
* **`REVIEW_REQUIRED`**: $< 0.60$ or any HIGH/CRITICAL review warning.

### 9.4 Review Reason Codes & Severity Catalog
* `LOW_OCR_CONFIDENCE` (`MEDIUM`)
* `CORRUPTED_TEXT` (`HIGH`)
* `INCOMPLETE_QUESTION` (`HIGH`)
* `MISSING_QUESTION_NUMBER` (`LOW`)
* `AMBIGUOUS_QUESTION_BOUNDARY` (`HIGH`)
* `INCOMPLETE_OPTIONS` (`MEDIUM`)
* `MISSING_OPTION` (`MEDIUM`)
* `MULTI_PAGE_UNCERTAINTY` (`HIGH`)
* `MISSING_SOURCE_REFERENCE` (`CRITICAL`)
* `UNMATCHED_ANSWER` (`MEDIUM`)
* `AMBIGUOUS_ANSWER` (`HIGH`)
* `CONFLICTING_ANSWER` (`HIGH`)
* `LOW_OVERALL_CONFIDENCE` (`HIGH` / `CRITICAL`)

### 9.5 Review Lifecycle & Deduplication
* **Deduplication**: Rerunning processing inspects existing `ReviewItem` records keyed by `(question_id, reason)`. Open items are updated in-place without duplicating; previously resolved/ignored items retain user resolution state; stale open items no longer detected are cleanly pruned.
* **Resolution**: Users can resolve (`RESOLVED`), ignore (`IGNORED`), or reopen (`OPEN`) review issues via `PATCH /api/v1/reviews/{id}`.

---

## 10. Docker Services Layout

| Service | Base Image | Role | Port Mapping | Volume Mounts | Health Probe |
|---|---|---|---|---|---|
| **`postgres`** | `postgres:16-alpine` | Relational database | `5432:5432` | `postgres_data` | `pg_isready` check |
| **`redis`** | `redis:7-alpine` | Broker and result store | `6379:6379` | `redis_data` | `redis-cli ping` |
| **`api`** | `python:3.12-slim` | FastAPI REST web server | `8000:8000` | `uploads_data` | HTTP `/api/v1/health` |
| **`worker`** | `python:3.12-slim` | Celery asynchronous worker | N/A | `uploads_data` | Celery inspect ping / process probe |

---

## 11. Roadmap to Phases 9–10

* **Phase 9**: Human-in-the-Loop Review Dashboard APIs & Collaboration.
* **Phase 10**: Production Hardening, Observability, Rate Limiting, and Performance Optimization.


