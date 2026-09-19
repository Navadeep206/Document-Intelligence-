import { apiClient } from './axios';
import {
  Document,
  DocumentListResponse,
  DocumentProcessingStatus,
  DocumentRole,
  DocumentUploadAcceptedResponse,
} from '@/types/document';
import { QuestionListResponse } from '@/types/question';
import { AnswerMappingListResponse } from '@/types/answer';
import { ReviewItemListResponse } from '@/types/review';

export async function uploadDocumentApi(
  file: File,
  role: DocumentRole = 'QUESTION_PAPER'
): Promise<DocumentUploadAcceptedResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_role', role);

  const response = await apiClient.post<DocumentUploadAcceptedResponse>('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
}

export async function getDocumentsApi(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  document_role?: string;
}): Promise<DocumentListResponse> {
  const response = await apiClient.get<DocumentListResponse>('/documents', { params });
  return response.data;
}

export async function getDocumentApi(id: string): Promise<Document> {
  const response = await apiClient.get<Document>(`/documents/${id}`);
  return response.data;
}

export async function getDocumentStatusApi(id: string): Promise<DocumentProcessingStatus> {
  const response = await apiClient.get<DocumentProcessingStatus>(`/documents/${id}/status`);
  return response.data;
}

export async function getDocumentQuestionsApi(
  id: string,
  params?: {
    page?: number;
    page_size?: number;
    status?: string;
    question_type?: string;
    review_required?: boolean;
  }
): Promise<QuestionListResponse> {
  const response = await apiClient.get<QuestionListResponse>(`/documents/${id}/questions`, { params });
  return response.data;
}

export async function getDocumentAnswerMappingsApi(
  id: string,
  params?: { page?: number; page_size?: number; status?: string }
): Promise<AnswerMappingListResponse> {
  const response = await apiClient.get<AnswerMappingListResponse>(`/documents/${id}/answer-mappings`, { params });
  return response.data;
}

export async function getDocumentReviewsApi(
  id: string,
  paramsOrStatus?: string | { status?: string; page?: number; page_size?: number }
): Promise<ReviewItemListResponse> {
  const params = typeof paramsOrStatus === 'string'
    ? { status: paramsOrStatus }
    : paramsOrStatus;
  const response = await apiClient.get<ReviewItemListResponse>(`/documents/${id}/reviews`, {
    params,
  });
  return response.data;
}

