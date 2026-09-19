export type DocumentRole = 'QUESTION_PAPER' | 'ANSWER_KEY' | 'SYLLABUS' | 'UNKNOWN';

export type DocumentStatus = 'PENDING' | 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'REVIEW_REQUIRED';

export interface Document {
  id: string;
  filename: string;
  document_type: string;
  document_role: DocumentRole;
  status: DocumentStatus;
  page_count: number | null;
  question_count?: number;
  review_count?: number;
  created_at: string;
}

export interface DocumentProcessingStatus {
  document_id: string;
  status: DocumentStatus;
  document_status?: DocumentStatus;
  pages_processed: number;
  total_pages: number | null;
  questions_extracted: number;
  review_required: boolean | number;
  error_message?: string | null;
  job?: {
    id: string;
    status: string;
    attempt: number;
    task_id: string;
    started_at: string | null;
    completed_at: string | null;
  } | null;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DocumentUploadAcceptedResponse {
  id: string;
  filename: string;
  status: DocumentStatus;
  job_id: string;
  created_at: string;
}
