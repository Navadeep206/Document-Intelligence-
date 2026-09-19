export type ReviewReason =
  | 'LOW_CONFIDENCE'
  | 'AMBIGUOUS_ANSWER'
  | 'INCOMPLETE_OPTIONS'
  | 'UNRESOLVED_CONTRADICTION'
  | 'MALFORMED_STRUCTURE'
  | 'OCR_UNCERTAINTY';

export type ReviewSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type ReviewStatus = 'OPEN' | 'RESOLVED' | 'IGNORED';

export interface ReviewItem {
  id: string;
  document_id: string;
  question_id: string | null;
  reason: ReviewReason;
  severity: ReviewSeverity;
  status: ReviewStatus;
  description: string | null;
  created_at: string;
  resolved_at?: string | null;
  notes?: string | null;
}

export interface ReviewItemListResponse {
  items: ReviewItem[];
  total: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
}
