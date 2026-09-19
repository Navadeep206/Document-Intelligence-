# Architectural Trade-Offs & Design Decisions

This document details the engineering trade-offs and rationale behind key architectural decisions made in the **Document Intelligence & Question Extraction Service**.

---

## 1. Why FastAPI?
* **High Performance**: Built on Starlette and Uvicorn, FastAPI provides asynchronous ASGI request handling with performance competitive with Go and Node.js.
* **Automatic OpenAPI/Swagger Documentation**: Schema definitions automatically generate interactive OpenAPI 3.0 documentation at `/docs` and `/redoc`, facilitating evaluator testing.
* **Native Type Safety & Validation**: Tight integration with Pydantic v2 ensures strict request/response data validation, automatic error serialization, and zero boilerplate parsing.
* **Asynchronous Concurrency**: Clean separation between async I/O routes (HTTP requests) and CPU-heavy operations (delegated to Celery workers).

---

## 2. Why PostgreSQL?
* **Relational Integrity & Normalization**: The problem domain consists of deeply interconnected entities: `users`, `documents`, `pages`, `questions`, `options`, `sources`, `answer_keys`, `mappings`, and `reviews`. PostgreSQL enforces foreign keys, unique constraints, and `ON DELETE CASCADE` integrity.
* **ACID Guarantees**: Exam and question ingestion require consistent multi-table state transitions that document stores cannot guarantee without complex distributed transactions.
* **SQL Indexing & Filtering**: Fast multi-tenant querying by `user_id`, document `status`, and question filters (`question_type`, `review_required`) is optimized via B-tree composite indices.

---

## 3. Why Redis + Celery?
* **Decoupled Architecture**: Keeps the web API gateway responsive by offloading heavy computational workloads to independent background processes.
* **Distributed Task Queue**: Celery provides battle-tested worker pooling, exponential backoff retries, dead-letter tracking, and task state management.
* **Lightweight Footprint**: Redis provides high-throughput in-memory brokering and results caching with minimal system memory (~30MB) compared to heavyweight Kafka or RabbitMQ clusters.

---

## 4. Why Asynchronous Processing?
* **Preventing Gateway Timeouts**: Extracting high-resolution PDFs or running OCR on multi-page scans can take 3–30 seconds. Synchronous processing would exhaust server threads and cause client HTTP timeouts.
* **Predictable SLA**: The API immediately acknowledges document uploads with `202 Accepted` in <50ms, returning a document ID that clients can poll for status telemetry.
* **Horizontal Scalability**: Worker instances can scale dynamically with workload demand independently of web API nodes.

---

## 5. Why Tesseract & PyMuPDF?
* **Zero External Cloud Dependencies**: Evaluators can run the entire extraction suite offline without configuring Google Cloud Vision or AWS Textract credentials.
* **High-Speed Native Extraction**: PyMuPDF (`fitz`) provides instantaneous direct extraction of embedded text, fonts, and vector geometry from digital PDFs.
* **Intelligent Dual-Engine Fallback**: Pages with digital text are parsed natively in milliseconds; pages with sparse text (<20 characters) or image-only scans automatically fallback to Tesseract OCR with image preprocessing (Otsu thresholding, grayscale).
* **Data Privacy**: Prevents academic examinations and sensitive student documents from leaking to external cloud vendors.

---

## 6. Why Deterministic Answer Matching?
* **Zero Hallucinations**: In academic testing, false positives can compromise exam integrity. Rule-based normalization matches answers only when explicit question references exist.
* **Explicit Uncertainty**: Ambiguous, conflicting, or uncertain mappings (e.g., `?`, `unclear`, multiple conflicting keys) are flagged as `UNMATCHED` or `AMBIGUOUS` rather than silently guessed.
* **Low Latency & Zero Cost**: Deterministic matching runs in <1ms without token costs or GPU inference latency.

---

## 7. Why Confidence Scoring + Human Review?
* **Graduated Trust Model**: Machine extraction cannot guarantee 100% accuracy on poor scans. A composite multi-signal confidence engine (evaluating OCR confidence, text density, boundary clarity, and options presence) scores every question from 0.0 to 1.0.
* **Actionable Review Queue**: Questions falling below the confidence threshold (0.85) or encountering structural issues (e.g., MCQ with <2 options) are automatically diverted to a human review queue with specific severity levels and explanatory reasons.
* **Auditability**: Review items record who reviewed, when, and resolution notes, maintaining complete provenance.

---

## 8. Why Source-Page & Bounding Box Traceability?
* **Verification in Context**: Questions link to specific `document_pages` and normalized coordinate bounding boxes (`x, y, width, height`), allowing UI clients to highlight the exact visual location of the question on the original exam sheet.
* **Multi-Page Continuity**: When a question spans across a page break (e.g., Question 5 starts on page 2 and options finish on page 3), tracking multiple page sources ensures text is neither truncated nor duplicated.

---

## 9. Why Local Storage Abstraction?
* **Zero-Setup Evaluator Experience**: Using an abstract `StorageService` interface with a `LocalStorageService` driver allows the system to run locally or in Docker without requiring S3 bucket provisioning or MinIO instances.
* **Path Traversal Security**: Uploaded files are renamed to randomized UUIDs (`{uuid4}.{ext}`) and stored strictly in an isolated directory outside the code package, with canonical path traversal checks.
* **Cloud-Ready Interface**: Swapping to AWS S3, Google Cloud Storage, or Azure Blob Storage in production requires only implementing the existing `StorageService` protocol (`save`, `get_absolute_path`, `delete`, `exists`).
