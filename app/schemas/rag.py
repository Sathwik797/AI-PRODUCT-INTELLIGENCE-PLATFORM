"""Pydantic schemas and DTO contracts for Phase 07.2 Grounded RAG.

Implements Q71-Q87 and V2 architecture contracts:
- Strongly typed RAG contracts: RAGVerifiedAttribute[], RAGEvidence, and constrained RAGClaimValueType
- Clean Prompt -> Provider boundary with typed RAGPromptPayload
- Provenance-aware evidence and citations
- Deterministic RAGModelResponse output contract for provider-native structured output
- Execution telemetry and API contracts
"""

from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


# Constrained value representation covering canonical fields, primitive attributes,
# and structured metadata containers (RangeValue, DimensionsValue, arrays, objects).
RAGClaimValueType = Union[str, int, float, bool, dict[str, Any], list[Any], None]


# ==============================================================================
# EVIDENCE & CITATION SCHEMAS
# ==============================================================================

class RAGEvidence(BaseModel):
    """Authoritative provenance for a verified catalog attribute or fact.

    Matches Phase 05 singular evidence semantics: each attribute is backed
    by a specific source (image, seller, inferred, or canonical_catalog).
    """
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["image", "seller", "inferred", "canonical_catalog"] = Field(
        ...,
        description="Origin of the verified fact: 'image', 'seller', 'inferred', or 'canonical_catalog'."
    )
    image_id: Optional[int] = Field(
        default=None,
        description="Exact database image ID when source_type is 'image'."
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Reasoning or description explaining how the evidence supports the attribute."
    )


class RAGCitation(BaseModel):
    """Claim citation pointing to verified accepted evidence."""
    model_config = ConfigDict(extra="forbid")

    image_id: Optional[int] = Field(
        default=None,
        description="Referenced image ID justifying the claim when grounded in visual evidence."
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Optional brief explanation of how the evidence justifies the claim."
    )


# ==============================================================================
# ATOMIC CLAIM & LLM RESPONSE CONTRACTS
# ==============================================================================

class RAGClaim(BaseModel):
    """Atomic evidence-grounded claim.

    The structured (product_id, attribute, value) triple is the deterministic
    verification anchor checked against accepted catalog metadata and evidence.
    The natural language `claim` is for human-readable presentation.
    """
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(
        ...,
        min_length=1,
        description="Natural-language assertion for human-readable presentation."
    )
    product_id: int = Field(
        ...,
        description="Authoritative database product ID that this claim applies to."
    )
    attribute: str = Field(
        ...,
        min_length=1,
        description="Target attribute name (e.g. 'price', 'material', 'color', 'brand', 'status')."
    )
    value: RAGClaimValueType = Field(
        ...,
        description="Structured attribute value for deterministic backend verification."
    )
    citation: Optional[RAGCitation] = Field(
        default=None,
        description="Evidence citation reference when required by fact provenance."
    )


class RAGModelResponse(BaseModel):
    """Provider-native structured output contract (Q78, Q82).

    Decouples clean conversational answer from structured atomic claims.
    No inline bracket citations in answer text.
    """
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(
        ...,
        description="Helpful, conversational synthesized answer grounded exclusively in supplied catalog context."
    )
    claims: list[RAGClaim] = Field(
        default_factory=list,
        description="List of atomic factual claims asserting specific product properties."
    )


# ==============================================================================
# KNOWLEDGE BUNDLE & CONTEXT CONTRACTS
# ==============================================================================

class RAGVerifiedAttribute(BaseModel):
    """A strongly-typed, accepted semantic attribute with provenance."""
    model_config = ConfigDict(extra="forbid")

    attribute: str = Field(..., description="Attribute name (e.g. 'material', 'color', 'weight').")
    type: str = Field(default="text", description="Semantic attribute type: text, number, boolean, measurement, range, dimensions, array, object.")
    value: RAGClaimValueType = Field(None, description="Normalized canonical attribute value.")
    unit: Optional[str] = Field(None, description="Measurement or range unit if applicable.")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="AI extraction confidence score.")
    evidence: Optional[RAGEvidence] = Field(None, description="Singular evidence provenance matching Phase 05 schema.")


class RAGProductContext(BaseModel):
    """Hydrated product context supplied to RAG (Q75, Q79).

    Explicitly separates live transactional facts (price, status), canonical facts,
    and verified semantic attributes with provenance.
    """
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(..., description="Product ID.")
    live_catalog_state: dict[str, Any] = Field(
        ...,
        description="Live transactional fields directly from relational Product row (price, status)."
    )
    product_facts: dict[str, Any] = Field(
        ...,
        description="Canonical product facts (title, description, brand, category)."
    )
    verified_attributes: list[RAGVerifiedAttribute] = Field(
        default_factory=list,
        description="Accepted AI-extracted attributes with proven source evidence."
    )
    search_match_context: list[str] = Field(
        default_factory=list,
        description="Retrieval provenance signals from hybrid search (NOT factual evidence)."
    )


class RAGKnowledgeBundle(BaseModel):
    """Read-time projection bundle containing retrieved and hydrated catalog knowledge (Q72, Q75)."""
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., description="User's natural language question.")
    products: list[RAGProductContext] = Field(
        default_factory=list,
        description="Hydrated product contexts bounded by max_context_products."
    )


# ==============================================================================
# PROMPT & PROVIDER PAYLOAD
# ==============================================================================

class RAGPromptPayload(BaseModel):
    """Clean, typed boundary between RAGPromptBuilder and RAGLLMProvider."""
    model_config = ConfigDict(extra="forbid")

    system_instruction: str = Field(..., description="System instructions governing grounding and output schema.")
    user_text: str = Field(..., description="Serialized JSON knowledge bundle and user query.")
    prompt_version: str = Field(default="rag_v1", description="Identifier of the prompt version.")


# ==============================================================================
# CONFIGURATION & TELEMETRY
# ==============================================================================

class RAGConfig(BaseModel):
    """Configuration for RAG subsystem."""
    model_config = ConfigDict(extra="ignore")

    max_context_products: int = Field(default=5, ge=1, le=10, description="Configurable top context products (Q76).")
    prompt_version: str = Field(default="rag_v1", description="Prompt builder version identifier (Q80).")
    model_name: str = Field(default="gemini-3.1-flash-lite", description="Runtime Gemini model name.")
    temperature: float = Field(default=0.2, ge=0.0, le=1.0, description="Sampling temperature.")
    max_output_tokens: int = Field(default=2048, ge=256, le=4096, description="Maximum tokens for generated response.")


class RAGTelemetry(BaseModel):
    """Minimal practical execution telemetry for RAG (Q86)."""
    model_config = ConfigDict(extra="forbid")

    total_latency_ms: float = Field(..., description="Total end-to-end execution time in milliseconds.")
    retrieval_latency_ms: float = Field(..., description="Time taken for hybrid search and context hydration.")
    llm_latency_ms: float = Field(..., description="Time taken by LLM provider for generation.")
    validation_latency_ms: float = Field(..., description="Time taken for citation and claim verification.")
    retry_count: int = Field(default=0, ge=0, le=1, description="Number of validation retries executed (0 or 1).")
    fallback_triggered: bool = Field(default=False, description="Whether deterministic fail-closed fallback was returned.")
    prompt_version: str = Field(..., description="Version of the prompt builder used.")
    model_name: str = Field(..., description="Actual runtime model used.")
    context_product_count: int = Field(..., description="Count of products provided in knowledge context.")
    input_tokens: Optional[int] = Field(default=None, description="Prompt tokens reported by provider.")
    output_tokens: Optional[int] = Field(default=None, description="Completion tokens reported by provider.")


# ==============================================================================
# API CONTRACTS
# ==============================================================================

class RAGQueryRequest(BaseModel):
    """Request contract for POST /api/v1/rag/query."""
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=500, description="User's natural language question.")


class RAGResponse(BaseModel):
    """Response contract for POST /api/v1/rag/query."""
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Original user query.")
    answer: str = Field(..., description="Grounded answer or deterministic fallback.")
    claims: list[RAGClaim] = Field(default_factory=list, description="Verified atomic claims.")
    retrieved_products: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Summaries of products retrieved and evaluated for context."
    )
    telemetry: RAGTelemetry = Field(..., description="Execution performance and operational telemetry.")
    status: Literal["success", "fallback", "no_results"] = Field(
        ...,
        description="Execution status: 'success', 'fallback' (on validation failure), or 'no_results'."
    )
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Explanation if fallback or no_results was triggered."
    )
