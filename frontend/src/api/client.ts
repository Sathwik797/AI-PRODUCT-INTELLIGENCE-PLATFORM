import axios, { AxiosError } from 'axios';

function normalizeApiBaseUrl(raw: unknown): string {
  if (!raw || typeof raw !== 'string') return '';
  let trimmed = raw.trim();
  if (!trimmed) return '';
  if (!trimmed.includes('.')) {
    trimmed = `${trimmed}.onrender.com`;
  }
  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  return withProtocol.replace(/\/+$/, '');
}

export const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_URL);

export const apiClient = axios.create({
  baseURL: API_BASE_URL ? API_BASE_URL : '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export function getFullApiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return API_BASE_URL ? `${API_BASE_URL}${cleanPath}` : cleanPath;
}

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: string | Array<{ msg: string }> }>;
    const detail = axiosError.response?.data?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((d) => d.msg || JSON.stringify(d)).join(', ');
    }
    return axiosError.message || 'An unexpected API error occurred';
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}
