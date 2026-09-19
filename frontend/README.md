# Document Intelligence & Question Extraction Dashboard — Frontend

Modern, high-density React + TypeScript web application for the **Document Intelligence & Question Extraction Service**.

---

## 1. Overview

This frontend connects to the FastAPI backend service to provide a streamlined operational dashboard for:
* Authenticating with Argon2id-hashed credentials and acquiring RFC-7519 JWT bearer tokens.
* Uploading multi-page question papers and official answer keys (PDF, JPG, PNG up to 25 MB).
* Monitoring real-time asynchronous Celery processing telemetry (`pages_processed`, `questions_extracted`, `status`).
* Inspecting structured questions, MCQ options, and source page provenance.
* Reviewing low-confidence questions, missing options, and ambiguous answer mappings.
* Resolving review warnings with operator audit notes.

---

## 2. Technology Stack

* **UI Framework**: React 19 + TypeScript
* **Build Tool & Dev Server**: Vite 8
* **Routing**: React Router 7 (`react-router-dom`)
* **HTTP Client**: Axios with automated bearer token interception and 401 redirect handling
* **Styling**: Tailwind CSS v3 with semantic status and typography tokens
* **Icons**: Lucide React

---

## 3. Environment Variables

Create `.env` from the provided template:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | Target FastAPI backend gateway base URL |

---

## 4. Development Setup

Ensure the backend API and worker are running (`http://localhost:8000`), then start the frontend:

```bash
# 1. Install dependencies
npm install

# 2. Start Vite development server (default port 3000)
npm run dev
```

The application will be available at:
👉 **`http://localhost:3000`**

---

## 5. Production Build

```bash
# Build type-checked production bundle to dist/
npm run build

# Preview production build locally
npm run preview
```

---

## 6. Project Architecture

```text
frontend/
├── src/
│   ├── api/                 # Centralized Axios client & domain API services
│   │   ├── axios.ts         # JWT interceptor, 401 handling, error formatting
│   │   ├── auth.ts          # Login, Register, Current User profile
│   │   ├── documents.ts     # Upload, list, status, questions, answer mappings
│   │   ├── questions.ts     # Question detail & question-specific reviews
│   │   └── reviews.ts       # Review queue listing & resolve endpoints
│   │
│   ├── components/
│   │   ├── ui/              # Reusable UI design system
│   │   │   ├── Button.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   ├── ConfidenceBadge.tsx
│   │   │   ├── Spinner.tsx
│   │   │   ├── Skeleton.tsx
│   │   │   ├── EmptyState.tsx
│   │   │   ├── ErrorState.tsx
│   │   │   ├── Modal.tsx
│   │   │   └── Pagination.tsx
│   │   │
│   │   └── documents/
│   │       └── DocumentUpload.tsx # Drag-and-drop validated upload component
│   │
│   ├── contexts/
│   │   └── AuthContext.tsx  # Global authentication context & token manager
│   │
│   ├── layouts/
│   │   └── DashboardLayout.tsx # Sidebar, Top Bar, User info & sign out
│   │
│   ├── pages/
│   │   ├── Login.tsx        # Authentication login view
│   │   ├── Register.tsx     # Account registration view
│   │   ├── Dashboard.tsx    # KPI stats, live upload, recent documents
│   │   ├── Documents.tsx    # Paginated documents repository with filters
│   │   ├── DocumentDetails.tsx # Document status polling, questions, reviews
│   │   ├── QuestionDetails.tsx # Structured question body, options & confidence
│   │   └── Reviews.tsx      # Human review queue & resolution modal
│   │
│   ├── routes/
│   │   └── AppRoutes.tsx    # Protected & public routing configuration
│   │
│   ├── types/               # TypeScript interfaces matching backend models
│   │   ├── auth.ts
│   │   ├── document.ts
│   │   ├── question.ts
│   │   ├── answer.ts
│   │   └── review.ts
│   │
│   ├── App.tsx              # Router & AuthProvider wrapper
│   ├── main.tsx             # Application bootstrap
│   └── index.css            # Tailwind layers & typography base
│
├── .env.example
├── package.json
├── tailwind.config.js
├── tsconfig.json
└── vite.config.ts
```
