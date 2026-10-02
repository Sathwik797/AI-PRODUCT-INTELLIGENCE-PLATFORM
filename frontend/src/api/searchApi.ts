import axios from 'axios';
import type { SearchResponse } from '../types/search';

export async function executeHybridSearch(
  q: string,
  limit: number = 20,
  debug: boolean = false
): Promise<SearchResponse> {
  const response = await axios.get<SearchResponse>('/api/v1/search', {
    params: { q, limit, debug },
  });
  return response.data;
}
