# Document Intelligence & Question Extraction Platform

Production-oriented backend platform engineered for scalable, automated processing of examination papers, question banks, and answer keys from scanned and digital documents (PDF, JPG, JPEG, PNG).

---

## 📌 Status: Phase 8 Complete (Confidence Engine & Human Review System)

* **Phase 1**: Project Foundation & Architecture (FastAPI, Celery, Redis, PostgreSQL)
* **Phase 2**: Database Architecture, Domain Models & Migrations (SQLAlchemy 2.0, Alembic)
* **Phase 3**: Authentication, Authorization & Secure Document Upload (Argon2id, JWT)
* **Phase 4**: Asynchronous Document Processing Pipeline (Celery Worker, Retries, Idempotency)
* **Phase 5**: Document Ingestion, Page Processing & Tesseract OCR
* **Phase 6**: Question Detection & Structured Extraction
* **Phase 7**: Answer-Key Detection, Extraction & Question Association
* **Phase 8**: Confidence Engine & Human Review System (8-signal explainable scoring, idempotent review sync, review APIs)

---

## 📁 Repository Structure

The complete backend service is located in [`document-intelligence-service/`](document-intelligence-service/):

* **Service Code & API**: [`document-intelligence-service/app/`](document-intelligence-service/app/)
* **Confidence Engine & Reviews**: [`document-intelligence-service/app/services/confidence/`](document-intelligence-service/app/services/confidence/)
* **Answer Extraction**: [`document-intelligence-service/app/services/answer_extraction/`](document-intelligence-service/app/services/answer_extraction/)
* **Question Extraction**: [`document-intelligence-service/app/services/extraction/`](document-intelligence-service/app/services/extraction/)
* **Database & Migrations**: [`document-intelligence-service/alembic/`](document-intelligence-service/alembic/)
* **Worker Tasks**: [`document-intelligence-service/app/workers/`](document-intelligence-service/app/workers/)
* **Docker & Compose**: [`document-intelligence-service/docker-compose.yml`](document-intelligence-service/docker-compose.yml)
* **Architecture Blueprints**: [`document-intelligence-service/docs/architecture.md`](document-intelligence-service/docs/architecture.md)
* **Full Documentation**: [`document-intelligence-service/README.md`](document-intelligence-service/README.md)
* **Test Suite (91 passing tests)**: [`document-intelligence-service/tests/`](document-intelligence-service/tests/)

---

## ⚡ Quick Start

```bash
cd document-intelligence-service

# Copy environment template
cp .env.example .env

# Run with Docker Compose
docker compose up --build

# Run test suite
pytest -v
```
