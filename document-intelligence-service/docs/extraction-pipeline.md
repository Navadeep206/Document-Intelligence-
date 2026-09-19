# Extraction Pipeline Architecture & Intelligent Parsing

This document details the multi-stage asynchronous processing, OCR extraction, question boundary detection, option parsing, answer key reconciliation, and confidence telemetry pipeline implemented in the **Document Intelligence & Question Extraction Service**.

---

## 1. End-to-End Pipeline Architecture

```text
Uploaded Document (PDF / Image)
      │
      ▼
Page Decomposition & Format Inspection (PyMuPDF / Pillow)
      │
      ├─── Native Digital Text Available? (>= 20 chars/page)
      │          ├── YES ──► Extract Digital Text Layer (100% fidelity)
      │          └── NO  ──► Preprocess & Rasterize (Grayscale, Deskew, Contrast)
      │                            │
      │                            ▼
      │                      Tesseract OCR Extraction (PSM 6 / 3) + Confidence Score
      │
      ▼
Text Normalization (Whitespace, Ligatures, Punctuation, Header/Footer stripping)
      │
      ▼
Question Boundary Detection (Multi-format Regex Scoring + Heading Filters)
      │
      ▼
Question Structure & Type Classification (MCQ, True/False, Short, Long, Numerical)
      │
      ▼
Option Parsing & Separation (Vertical & Inline Multi-Column Parsing)
      │
      ▼
Answer-Key Detection & Reconciliation (Deterministic Exact & Normalized Reference Matcher)
      │
      ▼
Weighted Confidence Engine (8 Measurable Signals -> Composite Score)
      │
      ▼
Human-in-the-Loop Review Triage (Flag Issues: Low OCR, Missing Options, Uncertain Mappings)
      │
      ▼
Relational Persistence (Documents, Pages, Questions, Options, Sources, AnswerKey, Reviews)
```

---

## 2. Page Decomposition & OCR Strategy

### 2.1 Native Text Extraction vs. OCR Fallback
- For digital PDFs, the pipeline uses **PyMuPDF (`fitz`)** to extract high-fidelity digital text directly from the document. This avoids OCR errors, preserves exact characters, and minimizes CPU compute.
- If digital text contains fewer than `MIN_NATIVE_TEXT_CHARS` (default: 20 characters), the page is treated as a scanned image.
- Scanned pages are rendered to high-resolution images at `OCR_DPI` (default: 250 DPI) and passed through image preprocessing (grayscale conversion, Otsu thresholding, noise reduction) before running **Tesseract OCR**.
- OCR confidence is captured per word/block and averaged into `DocumentPage.ocr_confidence`.

---

## 3. Question Boundary Detection

The `QuestionBoundaryDetector` analyzes text lines sequentially to identify question starts:

1. **Heading & Noise Filtering**:
   - Lines matching common exam sections (e.g. `SECTION A`, `PART I`, `INSTRUCTIONS`, `Page 1 of 5`) are discarded.
2. **Multi-Style Prefix Detection**:
   - Explicit prefixes: `Q1.`, `Question 1:`, `Question No. 12`
   - Standard numbering: `1.`, `1)`, `1:`, `1 -`, `01.`
   - Parenthesized numbering: `(1)`, `(12)`
   - Roman numerals: `I.`, `II.`, `III.`, `IV.`, `(I)`
3. **Contextual Question Scoring**:
   - Lines beginning with interrogative or action verbs (`Which`, `Calculate`, `Explain`, `Define`, `Find`, `What`) receive additional weighting.
   - Question blocks are demarcated and grouped with all succeeding lines until the next boundary candidate.

---

## 4. Option Parsing & Separation

The `OptionParser` isolates multiple-choice options from the question stem text:

- **Vertical Options**: Options appearing on dedicated lines (e.g. `(A) Venus`, `(B) Mars`).
- **Inline / Multi-Column Options**: Options horizontally embedded in a single line (e.g. `(A) Apple  (B) Banana  (C) Cherry  (D) Date`).
- Supports labels: `A-D`, `a-d`, `1-4`, with brackets `(A)`, `[A]`, or dot notations `A.`, `A)`.
- Extracted options are saved to `QuestionOption` with strict `position` order (1, 2, 3, 4), and stripped from the stored `question_text`.

---

## 5. Question Type Classification

The `QuestionTypeClassifier` classifies each question deterministically:

| Question Type | Heuristic Classification Rules |
| :--- | :--- |
| **`MCQ`** | 2 or more distinct multiple-choice options detected. |
| **`TRUE_FALSE`** | Options contain True/False, or question stem starts with "State whether true or false". |
| **`NUMERICAL`** | Stem contains keywords: `Calculate`, `Compute`, `Find the value`, `Solve for`. |
| **`LONG_ANSWER`** | Stem contains keywords: `Explain`, `Describe`, `Discuss`, `Derive`, `Prove that`. |
| **`SHORT_ANSWER`** | Stem contains keywords: `Define`, `What is`, `State the`, `Name any`, `List`. |
| **`UNKNOWN`** | Unstructured question without clear patterns. |

---

## 6. Multi-Page Question Handling

- Questions spanning across page breaks are handled via page sequence continuity.
- If a page ends without option completions or punctuation, and the subsequent page begins with continuation text (or remaining options `(C)`, `(D)`), the blocks are coalesced into a single `Question` record.
- Multiple `QuestionSource` entries link the unified question to all contributing `DocumentPage` records for full auditability.

---

## 7. Answer-Key Detection & Association

The `AnswerExtractor` detects and reconciles answer keys either from within the same document or an explicitly paired related document:

- **Grid and Single-Line Parsing**:
  - Grid: `1. A   2. B   3. C   4. D`
  - Single: `Q1: B`, `Question 15: True`, `12) D`
- **Reference Normalization**:
  - Normalizes `Q.1`, `Question 01`, `1.` into canonical index `1`.
- **Match Strategies**:
  - `EXACT`: Identical raw and normalized reference to a single question (`confidence = 0.98`).
  - `NORMALIZED`: Matches normalized number (`confidence = 0.92`).
  - `AMBIGUOUS`: Multiple questions share the same number. Matched question ID is withheld to prevent false assignments.
  - `UNCERTAIN`: Key contains `?`, `unclear`, or `unknown`. Never silently inferred.
  - `UNMATCHED`: Answer entry has no corresponding question in the document.

---

## 8. Confidence Engine & Human Review Triage

A composite confidence score (0.0 to 1.0) is evaluated across 8 weighted signals:
- OCR Quality (0.20)
- Text Quality (0.20)
- Boundary Confidence (0.15)
- Numbering Confidence (0.10)
- Option Completeness (0.10)
- Source Traceability (0.10)
- Page Validity (0.05)
- Answer Quality (0.10)

### Thresholds:
- **`EXTRACTED`** ($\ge 0.85$): High confidence extraction.
- **`PARTIAL`** ($0.60 \le \text{score} < 0.85$): Minor omissions (e.g. 1 option missing or moderate OCR).
- **`REVIEW_REQUIRED`** ($< 0.60$ or critical issues): Flagged for human review.
