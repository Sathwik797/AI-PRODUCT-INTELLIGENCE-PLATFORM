export interface RAGEvidence {
  source_type: 'image' | 'seller' | 'inferred' | 'canonical_catalog';
  image_id?: number | null;
  explanation?: string | null;
}

export interface RAGCitation {
  image_id?: number | null;
  explanation?: string | null;
}

export interface RAGClaim {
  claim: string;
  product_id: number;
  attribute: string;
  value: unknown;
  citation?: RAGCitation | null;
}

export interface RAGExecutionTelemetry {
  retrieved_candidate_count: number;
  extracted_claim_count: number;
  verified_claim_count: number;
  rejected_claim_count: number;
  execution_time_ms: number;
  citation_validation_passed: boolean;
  model: string;
  degraded_mode: boolean;
}

export interface RAGResponse {
  query: string;
  answer: string;
  claims: RAGClaim[];
  telemetry: RAGExecutionTelemetry;
  grounding_passed: boolean;
}

export interface RAGQueryRequest {
  query: string;
  limit?: number;
}
