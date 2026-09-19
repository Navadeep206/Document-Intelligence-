# Evaluator Demo Guide & Execution Scenarios

This guide presents the deterministic end-to-end demonstration flow for evaluators to test and review the **Document Intelligence & Question Extraction Service**.

---

## 1. Deterministic Demonstration Flow

The evaluator can follow this 13-step sequence to verify the complete capability surface of the service:

1. **Register / Login**: Create an isolated evaluator account and obtain a JWT bearer token.
2. **Upload Document**: Submit `samples/demo/digital_exam.pdf` via multipart upload.
3. **Receive Document ID**: Obtain immediate `202 Accepted` response with a UUID identifier.
4. **Check Processing Status**: Poll `GET /api/v1/documents/{id}/status` to observe the `PROCESSING` state.
5. **Wait for Completion**: Observe the status transition to `COMPLETED` with real-time processed page counts.
6. **Retrieve Questions**: Query `GET /api/v1/documents/{id}/questions` to view all extracted questions with pagination.
7. **Open Individual Question**: Query `GET /api/v1/questions/{id}` to view detailed question text, classification, and metadata.
8. **Inspect Options**: Verify structured option extraction for MCQ questions (`label`: "A"-"D", ordered sequence).
9. **Inspect Answer Association**: Link `samples/demo/answer_key.pdf` and inspect mapped answer values and match confidence.
10. **Inspect Confidence Score**: View composite multi-signal confidence scores (0.0 to 1.0).
11. **Inspect Source Pages**: Verify source page tracking (e.g., page 1, page 2) and bounding box coordinate geometry.
12. **Inspect Review Warnings**: Upload `samples/demo/low_quality_exam.pdf` to observe `REVIEW_REQUIRED` state and review warnings.
13. **Resolve Review Item**: Call `PATCH /api/v1/reviews/{id}` to transition an item from `OPEN` to `RESOLVED`.

---

## 2. Step-by-Step Evaluator Walkthrough Script

### Step 1: Start Services
Ensure Docker containers or local services (PostgreSQL, Redis, Celery worker, FastAPI) are running:
```bash
docker compose up -d
```

### Step 2: Open Swagger Documentation
Navigate to `http://localhost:8000/docs` in your browser. All endpoints are interactive and organized by domain tags.

### Step 3: Authenticate
Click **Authorize** (top right) or submit `/api/v1/auth/register` and `/api/v1/auth/login`. Paste the returned bearer token into the Swagger authorization dialog.

### Step 4: Upload Digital Exam Paper
Call `POST /api/v1/documents/upload` with:
* `file`: `samples/demo/digital_exam.pdf`
* `document_role`: `QUESTION_PAPER`

### Step 5: Observe Asynchronous Processing State
Immediately poll `GET /api/v1/documents/{id}/status`. Notice the rapid return of `status: "PROCESSING"`.

### Step 6: Verify Completed Processing State
Within 1–3 seconds, poll the status endpoint again. The status will transition to `COMPLETED` with:
* `pages_processed`: 2
* `total_pages`: 2
* `questions_extracted`: 4

### Step 7: Retrieve Extracted Questions
Call `GET /api/v1/documents/{id}/questions`. Notice 4 discrete questions parsed across the two pages without accidental boundary merging.

### Step 8: Inspect MCQ Options
Inspect question #1. Notice the structured options:
* `(A)` Quick Sort
* `(B)` Merge Sort
* `(C)` Bubble Sort
* `(D)` Selection Sort

### Step 9: Verify Source Page Traceability
Notice that question #1 notes `source_pages: [1]`, while question #4 spanning into the next page reflects `source_pages: [2]`.

### Step 10: Associate Official Answer Key
1. Call `POST /api/v1/documents/upload` with `samples/demo/answer_key.pdf` (`document_role: "ANSWER_KEY"`).
2. Call `POST /api/v1/documents/{id}/related` to link the answer key to the exam document.
3. Call `GET /api/v1/documents/{id}/answer-mappings` to observe verified answer associations (`Q1 -> B`, `Q2 -> A`, etc.) with `status: "MATCHED"`.

### Step 11: Upload Low-Quality / Uncertain Exam
Upload `samples/demo/low_quality_exam.pdf`. The backend triggers OCR fallback and evaluates confidence signals.

### Step 12: Observe Reduced Confidence
Call `GET /api/v1/documents/{id}/questions` on the low-quality document. Observe confidence scores dropping below the 0.85 threshold.

### Step 13: Observe REVIEW_REQUIRED State
Questions with reduced confidence or ambiguous boundaries transition to `status: "REVIEW_REQUIRED"` with `review_required: true`.

### Step 14: Inspect Human Review Queue
Call `GET /api/v1/documents/{id}/reviews`. Observe generated review items detailing specific reasons (e.g., `LOW_CONFIDENCE`, `INCOMPLETE_OPTIONS`, `OCR_UNCERTAINTY`).

### Step 15: Resolve Review Item
Call `PATCH /api/v1/reviews/{id}` with `status: "RESOLVED"` and explanatory notes. The review item resolves cleanly.

---

## 3. Assignment Scenarios Coverage

| Scenario | Demo File | Expected System Behavior | Verification Endpoint |
| :--- | :--- | :--- | :--- |
| **Scenario A: Digital PDF** | `digital_exam.pdf` | Direct digital text extraction, 100% confidence, structured MCQs | `GET /documents/{id}/questions` |
| **Scenario B: Image Upload** | `sample_question.jpg` | Direct image ingestion, Tesseract OCR fallback, detected question | `GET /documents/{id}/questions` |
| **Scenario C: Scanned / Degraded** | `low_quality_exam.pdf` | Automated OCR fallback, lowered confidence, flagged review | `GET /documents/{id}/reviews` |
| **Scenario D: Multi-question Page** | `digital_exam.pdf` | Clean segmentation of Questions 1, 2, 3 on Page 1 | `GET /documents/{id}/questions` |
| **Scenario E: Multi-page Question** | `multi_page_exam.pdf` | Cross-page continuation preserved with multiple page sources | `GET /questions/{id}` |
| **Scenario F: Answer Key Association** | `answer_key.pdf` | High-confidence matching of question numbers to answer keys | `GET /documents/{id}/answer-mappings` |
| **Scenario G: Ambiguous Answer** | `answer_key.pdf` | Uncertainty flags prevent silent guessing | `GET /documents/{id}/reviews` |
| **Scenario H: Invalid File Upload** | `corrupted.exe` | Strict magic byte check rejects upload with 400 Bad Request | `POST /documents/upload` |
