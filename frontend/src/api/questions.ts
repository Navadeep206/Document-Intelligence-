import { apiClient } from './axios';
import { Question } from '@/types/question';
import { ReviewItem, ReviewItemListResponse } from '@/types/review';

export async function getQuestionApi(id: string): Promise<Question> {
  const response = await apiClient.get<Question>(`/questions/${id}`);
  return response.data;
}

export async function getQuestionReviewsApi(id: string): Promise<ReviewItem[] | ReviewItemListResponse> {
  const response = await apiClient.get<ReviewItem[] | ReviewItemListResponse>(`/questions/${id}/reviews`);
  return response.data;
}

