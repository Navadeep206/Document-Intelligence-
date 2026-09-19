# Evaluator Quickstart Guide

This guide is designed for an evaluator to bring up the service, run tests, and test the API within 3 minutes.

---

## 1. Prerequisites

* **Docker & Docker Compose** (Recommended) — OR —
* **Local Python 3.12+**, **PostgreSQL 16**, **Redis 7**, and **Tesseract OCR** (`brew install tesseract` on macOS / `apt-get install tesseract-ocr` on Linux).

---

## 2. Option A: Quickstart with Docker (Recommended)

Run everything in self-contained containers:

```bash
# 1. Clone & enter project directory
cd document-intelligence-service

# 2. Build and start all services (Postgres, Redis, API, Celery Worker)
docker compose up --build -d

# 3. Check container status
docker compose ps
```

The API will be available at:
* **Interactive Swagger UI**: `http://localhost:8000/docs`
* **Health Check**: `http://localhost:8000/health`

---

## 3. Option B: Quickstart with Local Python Environment

```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env

# 4. Run database migrations (requires local Postgres running)
alembic upgrade head

# 5. Start Celery Worker (Terminal 1)
celery -A app.workers.celery_app.celery_app worker --loglevel=info

# 6. Start FastAPI Application (Terminal 2)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 4. Run the Automated Test Suite

The test suite runs hermetically in in-memory SQLite with zero external dependencies (Postgres/Redis not required):

```bash
# Run all 134 unit and integration tests
pytest -v
```

Expected result:
```text
============================= 134 passed in ~7.5s ==============================
```

---

## 5. Explore via Interactive Swagger UI

1. Open `http://localhost:8000/docs` in your browser.
2. Click on `POST /api/v1/auth/register` $\to$ **Try it out** $\to$ Execute with default test credentials.
3. Click on `POST /api/v1/auth/login` $\to$ Execute to retrieve your JWT access token.
4. Click the green **Authorize** button at the top right of the Swagger UI and paste:
   ```text
   Bearer <your-token>
   ```
5. Try `POST /api/v1/documents/upload` using any file in `samples/demo/` (e.g., `samples/demo/digital_exam.pdf`).
6. Try `GET /api/v1/documents/{id}/questions` using the returned `id` to see structured questions and options.

---

## 6. Pre-Packaged Demo Assets

All sample documents are located in:
* `samples/demo/digital_exam.pdf` — Clean multi-page exam paper.
* `samples/demo/scanned_exam.pdf` — Rasterized scan document testing OCR fallback.
* `samples/demo/low_quality_exam.pdf` — Degraded exam testing confidence penalties and review warnings.
* `samples/demo/multi_page_exam.pdf` — Question spanning page breaks.
* `samples/demo/answer_key.pdf` — Tabular and inline answer schedules.
* `samples/demo/sample_question.jpg` — Direct image upload testing image ingestion.

Expected structured output from these samples can be inspected in:
* `samples/output/final-example.json`
* `samples/output/review-example.json`
