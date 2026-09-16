"""Deterministic Citation & Claim Validator.

Implements Q73, Q74, Q79, Q83 and V2 corrections:
- Structured (product_id, attribute, value) is the verification anchor.
- Centralized normalization/extraction layer handles strings, numbers, booleans, and nested structures.
- Evidence provenance determines citation requirement:
  * Image evidence (source_type == 'image') requires matching image_id citation.
  * Canonical catalog facts (price, status, brand, category) and non-image evidence
    do not take image citations; spurious citations are rejected as UNSUPPORTED_CITATION.
- Deterministic error codes:
  * INVALID_PRODUCT_REFERENCE
  * INVALID_ATTRIBUTE
  * VALUE_MISMATCH
  * INVALID_IMAGE_REFERENCE
  * MISSING_REQUIRED_CITATION
  * UNSUPPORTED_CITATION
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from app.schemas.rag import (
    RAGClaim,
    RAGClaimValueType,
    RAGKnowledgeBundle,
    RAGModelResponse,
    RAGProductContext,
    RAGVerifiedAttribute,
)


@dataclass
class ValidationResult:
    """Outcome of deterministic citation and claim validation."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    feedback_text: str = ""


def normalize_value(val: Any) -> Any:
    """Deterministically normalizes attribute and claim values for strict comparison."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        # Treat float and int equally (e.g. 2499 == 2499.0)
        return float(val)
    if isinstance(val, str):
        return val.strip().lower()
    if isinstance(val, dict):
        # Check for RangeValue min/max
        if "min" in val and "max" in val:
            try:
                return {
                    "min": float(val["min"]),
                    "max": float(val["max"])
                }
            except (ValueError, TypeError):
                pass
        # Check for DimensionsValue length/width/height
        if "length" in val and "width" in val and "height" in val:
            try:
                return {
                    "length": float(val["length"]),
                    "width": float(val["width"]),
                    "height": float(val["height"])
                }
            except (ValueError, TypeError):
                pass
        return {str(k).strip().lower(): normalize_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [normalize_value(item) for item in val]
    return str(val).strip().lower()


class CitationValidator:
    """Deterministic validator for RAG atomic claims and citations."""

    def validate(
        self,
        response: RAGModelResponse,
        bundle: RAGKnowledgeBundle
    ) -> ValidationResult:
        """Validates all claims in the model response against the knowledge bundle.

        Args:
            response: Typed RAGModelResponse containing answer and atomic claims.
            bundle: The RAGKnowledgeBundle containing retrieved and hydrated catalog facts.

        Returns:
            ValidationResult with boolean validity flag, structured errors, and feedback text.
        """
        errors: list[str] = []

        # Index bundle products by product_id
        products_by_id: dict[int, RAGProductContext] = {
            p.product_id: p for p in bundle.products
        }

        for idx, claim in enumerate(response.claims, start=1):
            claim_errors = self._validate_single_claim(claim, products_by_id)
            for err in claim_errors:
                errors.append(f"Claim #{idx} [product_id={claim.product_id}, attribute='{claim.attribute}']: {err}")

        is_valid = len(errors) == 0
        feedback_text = "\n".join(errors) if errors else ""

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            feedback_text=feedback_text
        )

    def _validate_single_claim(
        self,
        claim: RAGClaim,
        products_by_id: dict[int, RAGProductContext]
    ) -> list[str]:
        """Validates a single claim against the retrieved catalog context."""
        errors: list[str] = []

        # 1. Product exists in retrieved bundle?
        product = products_by_id.get(claim.product_id)
        if not product:
            errors.append(f"INVALID_PRODUCT_REFERENCE - Product {claim.product_id} was not retrieved in catalog context.")
            return errors

        attr_key = claim.attribute.strip().lower()

        # 2. Live transactional catalog facts (price, status)
        if attr_key in ("price", "status"):
            live_val = product.live_catalog_state.get(attr_key)
            if live_val is None:
                errors.append(f"INVALID_ATTRIBUTE - Live field '{attr_key}' not found on product {product.product_id}.")
                return errors

            norm_claimed = normalize_value(claim.value)
            norm_actual = normalize_value(live_val)
            if norm_claimed != norm_actual:
                errors.append(
                    f"VALUE_MISMATCH - Live catalog {attr_key} expected '{live_val}', claimed '{claim.value}'."
                )

            # Live catalog facts do NOT take image citations
            if claim.citation and claim.citation.image_id is not None:
                errors.append(
                    f"UNSUPPORTED_CITATION - Live catalog fact '{attr_key}' does not take image citations; cited image_id={claim.citation.image_id} is unsupported."
                )
            return errors

        # 3. Canonical product facts (title, description, brand, category)
        if attr_key in ("title", "description", "brand", "category"):
            canon_val = product.product_facts.get(attr_key)
            norm_claimed = normalize_value(claim.value)
            norm_actual = normalize_value(canon_val)
            if norm_claimed != norm_actual:
                errors.append(
                    f"VALUE_MISMATCH - Canonical product fact '{attr_key}' expected '{canon_val}', claimed '{claim.value}'."
                )

            # Canonical product facts do NOT take image citations
            if claim.citation and claim.citation.image_id is not None:
                errors.append(
                    f"UNSUPPORTED_CITATION - Canonical fact '{attr_key}' does not take image citations; cited image_id={claim.citation.image_id} is unsupported."
                )
            return errors

        # 4. Verified semantic attributes
        matched_attr: Optional[RAGVerifiedAttribute] = None
        for va in product.verified_attributes:
            if va.attribute.strip().lower() == attr_key:
                matched_attr = va
                break

        if not matched_attr:
            errors.append(
                f"INVALID_ATTRIBUTE - Attribute '{claim.attribute}' is not an accepted verified attribute for product {product.product_id}."
            )
            return errors

        # Value comparison
        norm_claimed = normalize_value(claim.value)
        norm_actual = normalize_value(matched_attr.value)
        if norm_claimed != norm_actual:
            errors.append(
                f"VALUE_MISMATCH - Attribute '{claim.attribute}' expected '{matched_attr.value}', claimed '{claim.value}'."
            )

        # Provenance-driven citation verification
        ev = matched_attr.evidence
        if ev and ev.source_type == "image":
            # Must cite matching image_id
            if not claim.citation or claim.citation.image_id is None:
                errors.append(
                    f"MISSING_REQUIRED_CITATION - Attribute '{claim.attribute}' is grounded in image evidence (image_id={ev.image_id}) but claim provided no image citation."
                )
            elif claim.citation.image_id != ev.image_id:
                errors.append(
                    f"INVALID_IMAGE_REFERENCE - Attribute '{claim.attribute}' cited image_id={claim.citation.image_id}, expected image_id={ev.image_id}."
                )
        else:
            # Non-image provenance: must NOT fabricate an image citation
            if claim.citation and claim.citation.image_id is not None:
                source_name = ev.source_type if ev else "unspecified"
                errors.append(
                    f"UNSUPPORTED_CITATION - Attribute '{claim.attribute}' has provenance source '{source_name}', not visual evidence; citing image_id={claim.citation.image_id} is unsupported."
                )

        return errors
