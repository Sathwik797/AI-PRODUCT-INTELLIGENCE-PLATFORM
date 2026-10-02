import type { Product } from './product';

export interface SearchFilters {
  brand?: string | null;
  category?: string | null;
  category_id?: number | null;
  color?: string | null;
  size?: string | null;
  min_price?: number | null;
  max_price?: number | null;
}

export interface SearchResultItem {
  product: Product;
  score: number;
  match_reasons: string[];
}

export interface SearchMetadata {
  eligible_candidate_count: number;
  total_eligible: number;
  returned_count: number;
  requested_limit: number;
  took_ms: number;
  k_expanded: boolean;
  parsed_filters: SearchFilters;
  semantic_query: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResultItem[];
  metadata: SearchMetadata;
  debug_diagnostics?: Record<string, unknown> | null;
}
