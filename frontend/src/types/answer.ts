export type AnswerMatchStatus = 'MATCHED' | 'UNMATCHED' | 'AMBIGUOUS' | 'CONFLICT';

export interface AnswerMapping {
  id: string;
  document_id: string;
  question_id: string;
  question_number: string;
  answer_value: string;
  status: AnswerMatchStatus;
  confidence: number;
  created_at: string;
}

export interface AnswerMappingListResponse {
  items: AnswerMapping[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AnswerKey {
  id: string;
  document_id: string;
  exam_code?: string;
  raw_content: Record<string, string>;
  created_at: string;
}
