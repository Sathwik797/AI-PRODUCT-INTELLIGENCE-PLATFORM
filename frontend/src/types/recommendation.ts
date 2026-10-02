import type { Product } from './product';

export interface RecommendationCandidateSignals {
  semantic_similarity: number;
  category_affinity: number;
  attribute_overlap: number;
  price_similarity: number;
  brand_affinity: number;
}

export interface RecommendationItem {
  product: Product;
  score: number;
  match_reasons: string[];
}

export interface RecommendationMetadata {
  source_product_id: number;
  evaluated_candidates: number;
  returned_count: number;
  took_ms: number;
  faiss_candidate_count: number;
  mysql_candidate_count: number;
  degraded_mode: boolean;
}

export interface RecommendationResponse {
  source_product_id: number;
  recommendations: RecommendationItem[];
  metadata: RecommendationMetadata;
}
