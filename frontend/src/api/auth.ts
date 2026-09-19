import { apiClient } from './axios';
import { LoginCredentials, RegisterCredentials, TokenResponse, User } from '@/types/auth';

export async function loginApi(credentials: LoginCredentials): Promise<TokenResponse> {
  const response = await apiClient.post<TokenResponse>('/auth/login', credentials);
  return response.data;
}

export async function registerApi(credentials: RegisterCredentials): Promise<User> {
  const response = await apiClient.post<User>('/auth/register', credentials);
  return response.data;
}

export async function getCurrentUserApi(): Promise<User> {
  const response = await apiClient.get<User>('/auth/me');
  return response.data;
}
