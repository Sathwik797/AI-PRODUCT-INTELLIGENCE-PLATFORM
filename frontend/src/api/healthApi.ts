import axios from 'axios';
import type { HealthResponse, LivenessResponse, ReadinessResponse } from '../types/health';

export async function getReadiness(): Promise<ReadinessResponse> {
  const response = await axios.get<ReadinessResponse>('/ready');
  return response.data;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await axios.get<HealthResponse>('/health');
  return response.data;
}

export async function getLiveness(): Promise<LivenessResponse> {
  const response = await axios.get<LivenessResponse>('/live');
  return response.data;
}
