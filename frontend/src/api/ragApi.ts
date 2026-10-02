import axios from 'axios';
import type { RAGQueryRequest, RAGResponse } from '../types/rag';

export async function queryRAG(request: RAGQueryRequest): Promise<RAGResponse> {
  const response = await axios.post<RAGResponse>('/api/v1/rag/query', {
    query: request.query,
  });
  return response.data;
}
