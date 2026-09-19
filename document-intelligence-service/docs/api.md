# API Reference & Inventory — Document Intelligence & Question Extraction Service

This document provides a comprehensive inventory and specification for all public REST API endpoints available in the service.

---

## 1. Authentication & Identity

### 1.1 Register New User
* **Method**: `POST`
* **URL**: `/api/v1/auth/register`
* **Authentication**: None (Public)
* **Request Body** (`application/json`):
  ```json
  {
    "email": "user@example.com",
    "password": "StrongPassword123!"
  }
  ```
* **Success Response** (`201 Created`):
  ```json
  {
    "id": "7b8cfd52-19e4-4d82-b7aa-36cebe5ec811",
    "email": "user@example.com",
    "is_active": true,
    "created_at": "2026-09-19T10:00:00Z"
  }
  ```
* **Possible Errors**:
  * `400 Bad Request` — `EMAIL_EXISTS`: Email is already registered.
  * `422 Unprocessable Entity` — Invalid email format or password under 8 characters.

---

### 1.2 Login & Token Generation
* **Method**: `POST`
* **URL**: `/api/v1/auth/login`
* **Authentication**: None (Public)
* **Request Body** (`application/json`):
  ```json
  {
    "email": "user@example.com",
    "password": "StrongPassword123!"
  }
  ```
* **Success Response** (`200 OK`):
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 1800
  }
  ```
* **Possible Errors**:
  * `401 Unauthorized` — `INVALID_CREDENTIALS`: Incorrect email or password (timing attack protected).

---

### 1.3 Current User Profile
* **Method**: `GET`
* **URL**: `/api/v1/auth/me`
* **Authentication**: Bearer JWT (`Authorization: Bearer <token>`)
* **Success Response** (`200 OK`):
  ```json
  {
    "id": "7b8cfd52-19e4-4d82-b7aa-36cebe5ec811",
    "email": "user@example.com",
    "is_active": true,
    "created_at": "2026-09-19T10:00:00Z"
  }
  ```
* **Possible Errors**:
  * `401 Unauthorized` — `INVALID_TOKEN` / `EXPIRED_TOKEN`.

---

## 2. Document Ingestion & Management

### 2.1 Upload Document
* **Method**: `POST`
* **URL**: `/api/v1/documents/upload`
* **Authentication**: Bearer JWT
* **Content-Type**: `multipart/form-data`
* **Form Parameters**:
  * `file`: Binary file (PDF, JPG, JPEG, PNG, max 25MB).
  * `document_role` (optional, query or form): `QUESTION_PAPER` (default) or `ANSWER_KEY`.
* **Success Response** (`202 Accepted`):
  ```json
  {
    "id": "299102af-1c2b-4a23-a49a-5483cce5e98e",
    "filename": "digital_exam.pdf",
    "document_type": "PDF",
    "document_role": "QUESTION_PAPER",
    "status": "PROCESSING",
    "created_at": "2026-09-19T10:05:00Z"
  }
  ```
* **Possible Errors**:
  * `400 Bad Request` — `UNSUPPORTED_FILE_TYPE` or corrupted file header.
  * `413 Payload Too Large` — File exceeds configured 25MB threshold.
  * `401 Unauthorized`.

---

### 2.2 List User Documents
* **Method**: `GET`
* **URL**: `/api/v1/documents`
* **Authentication**: Bearer JWT
* **Query Parameters**:
  * `page` (int, default: 1)
  * `page_size` (int, default: 20)
  * `status` (string, optional: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`)
  * `document_role` (string, optional: `QUESTION_PAPER`, `ANSWER_KEY`)
* **Success Response** (`200 OK`):
  ```json
  {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1,
    "items": [
      {
        "id": "299102af-1c2b-4a23-a49a-5483cce5e98e",
        "filename": "digital_exam.pdf",
        "document_type": "PDF",
        "document_role": "QUESTION_PAPER",
        "status": "COMPLETED",
        "page_count": 2,
        "question_count": 4,
        "review_count": 0,
        "created_at": "2026-09-19T10:05:00Z"
      }
    ]
  }
  ```

---

### 2.3 Retrieve Document Details
* **Method**: `GET`
* **URL**: `/api/v1/documents/{id}`
* **Authentication**: Bearer JWT
* **Success Response** (`200 OK`):
  ```json
  {
    "id": "299102af-1c2b-4a23-a49a-5483cce5e98e",
    "filename": "digital_exam.pdf",
    "document_type": "PDF",
    "document_role": "QUESTION_PAPER",
    "status": "COMPLETED",
    "page_count": 2,
    "question_count": 4,
    "review_count": 0,
    "created_at": "2026-09-19T10:05:00Z"
  }
  ```
* **Possible Errors**:
  * `404 Not Found` — `DOCUMENT_NOT_FOUND` (if missing or belongs to another user).

---

### 2.4 Document Processing Status
* **Method**: `GET`
* **URL**: `/api/v1/documents/{id}/status`
* **Authentication**: Bearer JWT
* **Success Response** (`200 OK`):
  ```json
  {
    "document_id": "299102af-1c2b-4a23-a49a-5483cce5e98e",
    "status": "COMPLETED",
    "pages_processed": 2,
    "total_pages": 2,
    "questions_extracted": 4,
    "review_required": false,
    "error_message": null
  }
  ```

---

## 3. Question Detection & Extraction

### 3.1 List Extracted Questions
* **Method**: `GET`
* **URL**: `/api/v1/documents/{id}/questions`
* **Authentication**: Bearer JWT
* **Query Parameters**:
  * `page` (int, default: 1)
  * `page_size` (int, default: 20)
  * `status` (string, optional: `EXTRACTED`, `REVIEW_REQUIRED`, `CONFIRMED`)
  * `question_type` (string, optional: `MCQ`, `TRUE_FALSE`, `NUMERICAL`, `SHORT_ANSWER`, `LONG_ANSWER`)
  * `review_required` (boolean, optional: `true`, `false`)
  * `page_number` (int, optional)
* **Success Response** (`200 OK`):
  ```json
  {
    "total": 4,
    "page": 1,
    "page_size": 20,
    "total_pages": 1,
    "items": [
      {
        "id": "cb22a44e-b4d4-4f8c-81f7-7ca79158bbd0",
        "document_id": "299102af-1c2b-4a23-a49a-5483cce5e98e",
        "question_number": "1",
        "question_text": "Which sorting algorithm guarantees an O(n log n) worst-case time complexity?",
        "question_type": "MCQ",
        "status": "EXTRACTED",
        "confidence_score": 1.0,
        "review_required": false,
        "options": [
          {"id": "...", "label": "A", "text": "Quick Sort", "position": 1},
          {"id": "...", "label": "B", "text": "Merge Sort", "position": 2},
          {"id": "...", "label": "C", "text": "Bubble Sort", "position": 3},
          {"id": "...", "label": "D", "text": "Selection Sort", "position": 4}
        ],
        "source_pages": [1]
      }
    ]
  }
  ```

---

### 3.2 Get Single Question Detail
* **Method**: `GET`
* **URL**: `/api/v1/questions/{id}`
* **Authentication**: Bearer JWT
* **Success Response** (`200 OK`):
  ```json
  {
    "id": "cb22a44e-b4d4-4f8c-81f7-7ca79158bbd0",
    "document_id": "299102af-1c2b-4a23-a49a-5483cce5e98e",
    "question_number": "1",
    "question_text": "Which sorting algorithm guarantees an O(n log n) worst-case time complexity?",
    "question_type": "MCQ",
    "status": "EXTRACTED",
    "confidence_score": 1.0,
    "review_required": false,
    "options": [
      {"id": "...", "label": "A", "text": "Quick Sort", "position": 1},
      {"id": "...", "label": "B", "text": "Merge Sort", "position": 2},
      {"id": "...", "label": "C", "text": "Bubble Sort", "position": 3},
      {"id": "...", "label": "D", "text": "Selection Sort", "position": 4}
    ],
    "sources": [
      {
        "page_number": 1,
        "bounding_box": {"x": 50, "y": 100, "width": 500, "height": 80}
      }
    ]
  }
  ```
* **Possible Errors**:
  * `404 Not Found` — `QUESTION_NOT_FOUND`.

---

## 4. Answer Intelligence & Mappings

### 4.1 Get Document Answer Key
* **Method**: `GET`
* **URL**: `/api/v1/documents/{id}/answer-key`
* **Authentication**: Bearer JWT
* **Success Response** (`200 OK`):
  ```json
  {
    "id": "f516a8d1-419b-4b24-9ea9-a1b2c3d4e5f6",
    "document_id": "299102af-1c2b-4a23-a49a-5483cce5e98e",
    "exam_code": "CS101",
    "raw_content": {"1": "B", "2": "A", "3": "C", "4": "D"}
  }
  ```

---

### 4.2 List Answer Mappings
* **Method**: `GET`
* **URL**: `/api/v1/documents/{id}/answer-mappings`
* **Authentication**: Bearer JWT
* **Query Parameters**:
  * `page` (int, default: 1)
  * `page_size` (int, default: 20)
  * `status` (string, optional: `MATCHED`, `UNMATCHED`)
* **Success Response** (`200 OK`):
  ```json
  {
    "total": 4,
    "page": 1,
    "page_size": 20,
    "total_pages": 1,
    "items": [
      {
        "id": "993c12aa-...",
        "question_id": "cb22a44e-b4d4-4f8c-81f7-7ca79158bbd0",
        "question_number": "1",
        "answer_value": "B",
        "status": "MATCHED",
        "confidence": 0.98
      }
    ]
  }
  ```

---

## 5. Related Documents

### 5.1 Link Related Document (Parent $\leftrightarrow$ Answer Key)
* **Method**: `POST`
* **URL**: `/api/v1/documents/{id}/related`
* **Authentication**: Bearer JWT
* **Request Body** (`application/json`):
  ```json
  {
    "related_document_id": "e932ba81-79bb-41a2-8b43-851fec040989",
    "relationship_type": "ANSWER_KEY"
  }
  ```
* **Success Response** (`201 Created`):
  ```json
  {
    "id": "319451ab-...",
    "parent_document_id": "299102af-1c2b-4a23-a49a-5483cce5e98e",
    "related_document_id": "e932ba81-79bb-41a2-8b43-851fec040989",
    "relationship_type": "ANSWER_KEY",
    "created_at": "2026-09-19T10:10:00Z"
  }
  ```
* **Possible Errors**:
  * `400 Bad Request` — Invalid relationship or self-link.
  * `404 Not Found` — Either document not found.
  * `409 Conflict` — Relationship already established.

---

### 5.2 List Related Documents
* **Method**: `GET`
* **URL**: `/api/v1/documents/{id}/related`
* **Authentication**: Bearer JWT
* **Success Response** (`200 OK`):
  ```json
  {
    "items": [
      {
        "id": "319451ab-...",
        "related_document_id": "e932ba81-79bb-41a2-8b43-851fec040989",
        "relationship_type": "ANSWER_KEY",
        "created_at": "2026-09-19T10:10:00Z"
      }
    ]
  }
  ```

---

## 6. Human Review Workflow

### 6.1 List Document Review Items
* **Method**: `GET`
* **URL**: `/api/v1/documents/{id}/reviews`
* **Authentication**: Bearer JWT
* **Query Parameters**:
  * `status` (string, optional: `OPEN`, `RESOLVED`, `IGNORED`)
* **Success Response** (`200 OK`):
  ```json
  {
    "items": [
      {
        "id": "rev-101-abcd",
        "question_id": "8f91c3da-7d23-4c91-b951-e123456789ab",
        "reason": "INCOMPLETE_OPTIONS",
        "severity": "MEDIUM",
        "status": "OPEN",
        "description": "Question type is MCQ but fewer than 2 distinct options were detected.",
        "created_at": "2026-09-19T10:12:00Z"
      }
    ]
  }
  ```

---

### 6.2 List Question Review Items
* **Method**: `GET`
* **URL**: `/api/v1/questions/{id}/reviews`
* **Authentication**: Bearer JWT
* **Success Response** (`200 OK`):
  ```json
  {
    "items": [
      {
        "id": "rev-101-abcd",
        "question_id": "8f91c3da-7d23-4c91-b951-e123456789ab",
        "reason": "INCOMPLETE_OPTIONS",
        "severity": "MEDIUM",
        "status": "OPEN",
        "description": "Question type is MCQ but fewer than 2 distinct options were detected."
      }
    ]
  }
  ```

---

### 6.3 Resolve / Update Review Item
* **Method**: `PATCH`
* **URL**: `/api/v1/reviews/{id}`
* **Authentication**: Bearer JWT
* **Request Body** (`application/json`):
  ```json
  {
    "status": "RESOLVED",
    "notes": "Verified visually; missing option D added."
  }
  ```
* **Success Response** (`200 OK`):
  ```json
  {
    "id": "rev-101-abcd",
    "status": "RESOLVED",
    "notes": "Verified visually; missing option D added.",
    "resolved_at": "2026-09-19T10:15:00Z"
  }
  ```
* **Possible Errors**:
  * `404 Not Found` — `REVIEW_ITEM_NOT_FOUND`.

---

## 7. Service Health & Diagnostics

### 7.1 Liveness Probe
* **Method**: `GET`
* **URL**: `/health` (and `/api/v1/health`)
* **Authentication**: None (Public)
* **Success Response** (`200 OK`):
  ```json
  {
    "status": "healthy",
    "version": "1.0.0",
    "timestamp": "2026-09-19T10:00:00Z"
  }
  ```

---

### 7.2 Readiness Probe
* **Method**: `GET`
* **URL**: `/health/ready`
* **Authentication**: None (Public)
* **Success Response** (`200 OK`):
  ```json
  {
    "status": "ready",
    "database": "connected",
    "redis": "connected",
    "timestamp": "2026-09-19T10:00:00Z"
  }
  ```
* **Possible Errors**:
  * `503 Service Unavailable` if database or Redis connectivity check fails.
