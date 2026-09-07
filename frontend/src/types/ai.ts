import type { Product } from './product';

export type EvidenceSource =
  | { type: 'image'; image_id: number }
  | { type: 'seller' }
  | { type: 'inferred' };

export interface Evidence {
  source: EvidenceSource;
  explanation: string;
}

export interface RangeValue {
  min: number;
  max: number;
}

export interface DimensionsValue {
  length: number;
  width: number;
  height: number;
}

export type TypedNode =
  | { type: 'text'; value: string | null }
  | { type: 'number'; value: number | null }
  | { type: 'boolean'; value: boolean | null }
  | { type: 'measurement'; value: number | null; unit?: string | null }
  | { type: 'range'; value: RangeValue | null; unit?: string | null }
  | { type: 'dimensions'; value: DimensionsValue | null; unit?: string | null }
  | { type: 'array'; value: TypedNode[] | null }
  | { type: 'object'; value: Record<string, TypedNode> | null };

export interface TextField {
  type: 'text';
  value: string | null;
  confidence: number;
  evidence: Evidence;
}

export interface CategoryRecommendationValue {
  recommended_category_id: number | null;
  recommended_category_name: string | null;
  proposed_category: string | null;
}

export interface CategoryField {
  value: CategoryRecommendationValue | null;
  confidence: number;
  evidence: Evidence;
}

export type AttributeField =
  | (TextField & { type: 'text' })
  | { type: 'number'; value: number | null; confidence: number; evidence: Evidence }
  | { type: 'boolean'; value: boolean | null; confidence: number; evidence: Evidence }
  | { type: 'measurement'; value: number | null; unit?: string | null; confidence: number; evidence: Evidence }
  | { type: 'range'; value: RangeValue | null; unit?: string | null; confidence: number; evidence: Evidence }
  | { type: 'dimensions'; value: DimensionsValue | null; unit?: string | null; confidence: number; evidence: Evidence }
  | { type: 'array'; value: TypedNode[] | null; confidence: number; evidence: Evidence }
  | { type: 'object'; value: Record<string, TypedNode> | null; confidence: number; evidence: Evidence };

export interface AIProductMetadata {
  title: TextField;
  description: TextField;
  brand: TextField;
  category: CategoryField;
  tags: string[];
  keywords: string[];
  attributes: Record<string, AttributeField>;
}

export type AcceptanceStatus = 'pending' | 'accepted' | 'modified' | 'rejected';

export interface AIGenerationStatusResponse {
  generation_id: number;
  product_id: number;
  generation_number: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  output: AIProductMetadata | null;
  acceptance_state: Record<string, AcceptanceStatus> | null;
  processing_time: number | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
}

export interface AIGenerationTriggerResponse {
  generation_id: number;
  product_id: number;
  status: string;
}

export type FieldReviewAction = 'accept' | 'modify' | 'reject' | 'pending';

export interface FieldReviewDecision {
  action: FieldReviewAction;
  modified_value?: unknown;
}

export interface AIAcceptSelectedRequest {
  decisions: Record<string, FieldReviewDecision>;
}

export interface AIAcceptanceResponse {
  product_id: number;
  generation_id: number;
  acceptance_state: Record<string, AcceptanceStatus>;
  applied_fields: string[];
  product: Product;
}
