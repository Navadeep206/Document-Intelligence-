export type QuestionType = 'MCQ' | 'TRUE_FALSE' | 'NUMERICAL' | 'SHORT_ANSWER' | 'LONG_ANSWER';

export type QuestionStatus = 'EXTRACTED' | 'REVIEW_REQUIRED' | 'CONFIRMED' | 'REJECTED';

export interface QuestionOption {
  id: string;
  question_id: string;
  label: string;
  option_text: string;
  position: number;
  created_at: string;
}

export interface QuestionSource {
  id: string;
  document_page_id: string;
  page_sequence: number;
  created_at: string;
}

export interface Question {
  id: string;
  document_id: string;
  question_number: string | null;
  question_text: string;
  question_type: QuestionType;
  status: QuestionStatus;
  confidence_score: number | null;
  review_required: boolean;
  options?: QuestionOption[];
  sources?: QuestionSource[];
  created_at: string;
}

export interface QuestionListResponse {
  document_id?: string;
  items: Question[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
