"""Pure, Stateless RAG Prompt Builder.

Implements Q80:
- Versioned prompt builder (rag_v1).
- Pure, stateless transformation (zero DB, zero network, zero side-effects).
- Serializes RAGKnowledgeBundle to clean structured JSON.
- Produces typed RAGPromptPayload (system_instruction, user_text, prompt_version).
- Dedicated correction feedback section for Attempt 2 retries.
"""

import json
from typing import Any, Optional

from app.schemas.rag import RAGKnowledgeBundle, RAGPromptPayload


class RAGPromptBuilder:
    """Pure, deterministic prompt builder for Grounded RAG."""

    PROMPT_VERSION: str = "rag_v1"

    def build(
        self,
        bundle: RAGKnowledgeBundle,
        retry_feedback: Optional[str] = None
    ) -> RAGPromptPayload:
        """Builds a typed prompt payload from the knowledge bundle and optional retry feedback.

        Args:
            bundle: RAGKnowledgeBundle containing retrieved and hydrated products.
            retry_feedback: Optional deterministic validation failure feedback for retry.

        Returns:
            Typed RAGPromptPayload ready for RAGLLMProvider.
        """
        system_instruction = self._build_system_instruction()
        user_text = self._build_user_text(bundle, retry_feedback)

        return RAGPromptPayload(
            system_instruction=system_instruction,
            user_text=user_text,
            prompt_version=self.PROMPT_VERSION
        )

    def _build_system_instruction(self) -> str:
        """Constructs strict grounding instructions for the LLM."""
        return (
            "You are a grounded e-commerce product intelligence assistant.\n\n"
            "STRICT GROUNDING & VERIFICATION RULES:\n"
            "1. Rely EXCLUSIVELY on the supplied catalog knowledge. Do NOT assume, extrapolate, or invent product features.\n"
            "2. LIVE CATALOG FACTS: Product 'price' and 'status' are live transactional facts directly from the database.\n"
            "3. ATOMIC FACTUAL CLAIMS: Every factual statement you make about a product in your answer must have a corresponding "
            "atomic entry in the 'claims' array.\n"
            "4. CLAIM STRUCTURE: Each claim must specify:\n"
            "   - 'claim': Human-readable presentation sentence.\n"
            "   - 'product_id': The exact product ID.\n"
            "   - 'attribute': The target attribute (e.g. 'price', 'status', 'brand', 'color', 'material').\n"
            "   - 'value': The structured value (e.g. 2499.0, 'ACTIVE', 'Leather', 'Black'). Must correspond to the supplied catalog data.\n"
            "   - 'citation': Citation object when required by evidence provenance.\n"
            "5. EVIDENCE CITATION PROVENANCE:\n"
            "   - When an attribute provides image evidence (with an 'image_id'), you MUST include a citation referencing that exact 'image_id'.\n"
            "   - Live catalog facts (price, status) and canonical facts (title, description, brand, category) do NOT require an image citation.\n"
            "   - Non-image attributes (seller or inferred source) must NOT fabricate or reference an image citation.\n"
            "   - Never invent or hallucinate an image ID not present in the evidence.\n"
            "6. SEARCH MATCH REASONS: Search match reasons are retrieval signals only. They are NOT factual catalog evidence.\n"
            "7. UNKNOWN INFORMATION: If an attribute or specification is not present in the supplied context, explicitly state that "
            "it is unavailable. Do NOT guess.\n"
            "8. ANSWER STYLE: Provide a natural, concise, and helpful conversational answer. Do NOT embed bracket citations (e.g. [1], [Image 1]) "
            "in the answer text. All citations belong exclusively in the structured 'claims' array.\n"
            "9. OUTPUT FORMAT: Return a single JSON object strictly conforming to the RAGModelResponse schema containing 'answer' and 'claims'."
        )

    def _build_user_text(
        self,
        bundle: RAGKnowledgeBundle,
        retry_feedback: Optional[str] = None
    ) -> str:
        """Serializes the knowledge bundle into structured JSON context."""
        context_payload: list[dict[str, Any]] = []

        for p in bundle.products:
            verified_attrs_list: list[dict[str, Any]] = []
            for va in p.verified_attributes:
                attr_dict: dict[str, Any] = {
                    "attribute": va.attribute,
                    "type": va.type,
                    "value": va.value,
                }
                if va.unit:
                    attr_dict["unit"] = va.unit
                if va.confidence is not None:
                    attr_dict["confidence"] = va.confidence
                if va.evidence:
                    attr_dict["evidence"] = {
                        "source_type": va.evidence.source_type,
                        "image_id": va.evidence.image_id,
                        "explanation": va.evidence.explanation,
                    }
                verified_attrs_list.append(attr_dict)

            context_payload.append({
                "product_id": p.product_id,
                "live_catalog_state": p.live_catalog_state,
                "product_facts": p.product_facts,
                "verified_attributes": verified_attrs_list,
                "search_match_context": p.search_match_context,
            })

        user_parts: list[str] = [
            f"USER QUESTION: {bundle.question}",
            "\nAVAILABLE CATALOG CONTEXT (Structured JSON):",
            json.dumps(context_payload, indent=2),
        ]

        if retry_feedback:
            user_parts.append("\n" + "=" * 50)
            user_parts.append("### CORRECTION FEEDBACK FROM PREVIOUS ATTEMPT")
            user_parts.append("Your previous response failed deterministic citation/claim verification:")
            user_parts.append(retry_feedback)
            user_parts.append(
                "Please fix these specific discrepancies in your answer and claims. "
                "Ensure every structured claim exactly matches the catalog values and evidence IDs above, "
                "or omit unverified claims entirely."
            )
            user_parts.append("=" * 50)

        return "\n".join(user_parts)
