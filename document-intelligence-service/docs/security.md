# Security & Compliance Architecture

The **Document Intelligence & Question Extraction Service** is engineered with security, privacy, tenant isolation, and defense-in-depth principles across all API boundaries, processing layers, and storage systems.

---

## 1. Authentication Architecture

- **Argon2id Password Hashing**:
  - User passwords are never persisted in plaintext. Passwords are salted and hashed using `argon2id`, configured to resist GPU/ASIC parallelized offline brute-force attacks.
  - Mitigates timing attacks on login attempts: if an email is not registered, a dummy Argon2id verification routine is executed to maintain uniform execution time and prevent user enumeration.
- **Stateless Cryptographic JWT Access Tokens**:
  - Signed using HMAC-SHA256 (`HS256`) with a cryptographically secure 256-bit secret key.
  - Standard payload incorporates subject identifier (`sub` as user UUID), issuance timestamp (`iat`), and strict expiration (`exp`, default 30 minutes).
  - Validated via FastAPI OAuth2 Bearer dependencies (`get_current_user`), enforcing active user status (`is_active == True`).

---

## 2. Multi-Tenant Authorization & Data Isolation

- **Owner-Scoped Queries**:
  - Every protected resource (documents, extracted pages, questions, answer keys, answer mappings, and review items) is tied to its originating tenant (`owner_id`).
  - Queries join and filter by `Document.owner_id == current_user.id`.
- **Enumeration Defense via HTTP 404**:
  - If User A attempts to read or mutate User B's document, question, or review, the service responds with `HTTP 404 Not Found` (rather than `403 Forbidden`).
  - This prevents malicious actors from probing valid UUID identifiers to map out data existences.

---

## 3. Upload Validation & Defense-in-Depth

The service validates incoming files across four independent verification barriers before any file touches disk or downstream parsers:

1. **Extension Whitelisting**:
   - Only `.pdf`, `.jpg`, `.jpeg`, and `.png` extensions are permitted.
2. **MIME Type Verification**:
   - The HTTP `Content-Type` header is inspected against supported types (`application/pdf`, `image/jpeg`, `image/png`).
   - MIME type is cross-referenced with the extension to reject extension spoofing (e.g. executable renamed to `.pdf`).
3. **Magic Byte Signature Inspection**:
   - The initial file bytes are evaluated against canonical format signatures:
     - PDF: `%PDF-` (`0x25 0x50 0x44 0x46 0x2D`)
     - PNG: `\x89PNG\r\n\x1a\n` (`0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A`)
     - JPEG/JPG: `\xFF\xD8\xFF`
   - Rejects corrupted or malicious files disguised as supported formats.
4. **Streaming Chunk-Based Size Enforcement**:
   - Uploads are streamed in 1 MB chunks up to the configured limit (`MAX_UPLOAD_SIZE_MB`, default 25 MB).
   - If accumulated bytes exceed the threshold, transfer aborts immediately with `HTTP 413 Payload Too Large`, preventing denial-of-service (DoS) memory exhaustion attacks.
5. **Path Traversal & Filename Sanitization**:
   - Filenames are sanitized via `Path(upload_file.filename).name`. Directory traversal tokens (`../`, `..\\`) and system paths (`/etc/`, `C:\`) are stripped.

---

## 4. Storage Isolation

- **Randomized Opaque Storage Keys**:
  - Uploaded files are persisted using cryptographically generated UUIDv4 keys (e.g., `a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf`).
  - The client's original filename is preserved in relational database metadata for human display only.
- **Filesystem Segregation**:
  - Storage directories (`./storage/uploads`) exist strictly outside application source code directories.
  - Physical filesystem storage paths are never exposed in public API responses.

---

## 5. Centralized Error Handling & Information Leak Prevention

- **Standardized Error Envelope**:
  - All client responses adhere to:
    ```json
    {
      "error": {
        "code": "DOCUMENT_NOT_FOUND",
        "message": "Document not found",
        "details": null
      }
    }
    ```
- **Traceback & Credential Shielding**:
  - In production, unhandled exceptions return generic `HTTP 500 Internal Server Error` with `code: INTERNAL_SERVER_ERROR`.
  - Detailed diagnostic logs and Python stack traces are written exclusively to server-side logs.
  - Database connection strings, passwords, JWT secrets, and internal filesystem paths are never leaked in HTTP response bodies.

---

## 6. Secret Management

- Configuration is managed via Pydantic `BaseSettings` reading from `.env` environment variables.
- Repository contains `.env.example` with placeholders only.
- Real secrets, tokens, and database passwords are never committed to version control.
