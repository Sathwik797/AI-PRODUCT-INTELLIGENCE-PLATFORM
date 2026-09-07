import { apiClient } from './client';
import type {
  AIGenerationStatusResponse,
  AIGenerationTriggerResponse,
  AIAcceptSelectedRequest,
  AIAcceptanceResponse,
  FieldReviewDecision,
} from '../types/ai';

export async function triggerAIGeneration(productId: number): Promise<AIGenerationTriggerResponse> {
  const response = await apiClient.post<AIGenerationTriggerResponse>(
    `/products/${productId}/ai/generate`
  );
  return response.data;
}

export async function getAIGenerationStatus(
  productId: number,
  generationId: number
): Promise<AIGenerationStatusResponse> {
  const response = await apiClient.get<AIGenerationStatusResponse>(
    `/products/${productId}/ai/generations/${generationId}`
  );
  return response.data;
}

export async function getCurrentAIGeneration(
  productId: number
): Promise<AIGenerationStatusResponse | null> {
  try {
    const response = await apiClient.get<AIGenerationStatusResponse>(
      `/products/${productId}/ai/current`
    );
    return response.data;
  } catch (error: unknown) {
    // If 404, product has no current generation pointer yet
    return null;
  }
}

export async function acceptAllAIMetadata(productId: number): Promise<AIAcceptanceResponse> {
  const response = await apiClient.post<AIAcceptanceResponse>(
    `/products/${productId}/ai/accept-all`
  );
  return response.data;
}

export async function reviewAIMetadata(
  productId: number,
  decisions: Record<string, FieldReviewDecision>
): Promise<AIAcceptanceResponse> {
  const payload: AIAcceptSelectedRequest = { decisions };
  const response = await apiClient.post<AIAcceptanceResponse>(
    `/products/${productId}/ai/review`,
    payload
  );
  return response.data;
}
