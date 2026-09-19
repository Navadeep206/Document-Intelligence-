import { apiClient } from './axios';
import { ReviewItem, ReviewItemListResponse } from '@/types/review';

export async function getReviewsApi(params?: {
  status?: string;
  document_id?: string;
}): Promise<ReviewItemListResponse> {
  const response = await apiClient.get<ReviewItemListResponse>('/reviews', { params });
  return response.data;
}

export async function resolveReviewApi(
  id: string,
  payload: { status: 'RESOLVED' | 'IGNORED'; notes?: string }
): Promise<ReviewItem> {
  const response = await apiClient.patch<ReviewItem>(`/reviews/${id}`, payload);
  return response.data;
}
