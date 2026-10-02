import axios from 'axios';
import type { RecommendationResponse } from '../types/recommendation';

export async function getProductRecommendations(
  productId: number,
  limit: number = 5
): Promise<RecommendationResponse> {
  const response = await axios.get<RecommendationResponse>(
    `/api/v1/products/${productId}/recommendations`,
    {
      params: { limit },
    }
  );
  return response.data;
}
