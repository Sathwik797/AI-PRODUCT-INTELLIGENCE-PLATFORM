"""Gemini AI Provider for AI Product Intelligence Platform.

Phase 05 – Step 3A: AI Provider Foundation.

This module provides the boundary between the internal AI service orchestration and
the Google Gemini API. It handles:
- Constructing multimodal requests with multiple images while preserving image identity (image_id).
- Injecting product/seller context and existing taxonomy.
- Requesting structured output conforming to the AIProductMetadata schema contract.
- Validating the output against the Pydantic AIProductMetadata contract.
- Translating SDK/API failures into strongly-typed provider exceptions.

Architectural Boundaries:
- NO SQLAlchemy models are accepted or queried.
- NO FastAPI UploadFile or HTTP exceptions are used.
- NO database persistence or seller acceptance logic.
- NO file storage logic; image bytes/paths are supplied via AIImageInput.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.schemas.ai_metadata import AIProductMetadata


# ==============================================================================
# PROVIDER EXCEPTIONS
# ==============================================================================

class GeminiProviderError(Exception):
    """Base exception for all Gemini provider errors."""
    pass


class GeminiConfigurationError(GeminiProviderError):
    """Raised when Gemini configuration (e.g. API key) or SDK is missing."""
    pass


class GeminiResponseValidationError(GeminiProviderError):
    """Raised when the AI response fails validation against AIProductMetadata schema."""
    pass


class GeminiAPIError(GeminiProviderError):
    """Raised when the underlying Gemini API call fails (network, quota, model error)."""
    pass


# ==============================================================================
# PROVIDER INPUT BOUNDARY (Decoupled from DB & HTTP)
# ==============================================================================

@dataclass
class AIImageInput:
    """Individual product image input for multimodal AI reasoning.

    Preserves image_id so the model can cite exact evidence sources.
    """
    image_id: int
    image_bytes: Optional[bytes] = None
    file_path: Optional[str] = None
    mime_type: str = "image/jpeg"
    display_order: Optional[int] = None
    role: Optional[str] = None  # Optional seller image-role override (e.g., 'front', 'packaging', 'label')

    def get_bytes(self) -> bytes:
        """Retrieves raw image bytes from memory or file path."""
        if self.image_bytes is not None:
            return self.image_bytes
        if self.file_path is not None:
            path = Path(self.file_path)
            if not path.exists():
                raise GeminiProviderError(f"Image file not found at path: {self.file_path}")
            return path.read_bytes()
        raise GeminiProviderError(f"Image {self.image_id} has neither bytes nor file_path specified.")


@dataclass
class AIProductContext:
    """Explicit context passed to the Gemini Provider.

    Contains seller inputs, existing taxonomy, and all available product images.
    Decoupled entirely from SQLAlchemy models.
    """
    product_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[float] = None
    category_hint: Optional[str] = None
    current_category: Optional[str] = None
    existing_categories: list[Any] = field(default_factory=list)
    available_categories: list[Any] = field(default_factory=list)
    images: list[AIImageInput] = field(default_factory=list)

    def __post_init__(self):
        # Synchronize category_hint and current_category for seamless interoperability
        if not self.current_category and self.category_hint:
            self.current_category = self.category_hint
        elif not self.category_hint and self.current_category:
            self.category_hint = self.current_category

        # Synchronize existing_categories and available_categories
        if not self.available_categories and self.existing_categories:
            self.available_categories = list(self.existing_categories)
        elif not self.existing_categories and self.available_categories:
            self.existing_categories = list(self.available_categories)

        # Normalize taxonomy categories to list of dicts: {"id": Optional[int], "name": str}
        normalized: list[dict[str, Any]] = []
        for cat in self.available_categories:
            if isinstance(cat, dict):
                c_id = cat.get("id")
                try:
                    c_id = int(c_id) if c_id is not None else None
                except (ValueError, TypeError):
                    c_id = None
                c_name = str(cat.get("name") or "").strip()
                if c_name:
                    normalized.append({"id": c_id, "name": c_name})
            elif isinstance(cat, str):
                c_name = cat.strip()
                if c_name:
                    normalized.append({"id": None, "name": c_name})
            else:
                raw_id = getattr(cat, "id", None)
                c_id = None
                if raw_id is not None and not type(raw_id).__name__.startswith("MagicMock"):
                    try:
                        c_id = int(raw_id)
                    except (ValueError, TypeError):
                        c_id = None
                c_name = str(getattr(cat, "name", str(cat)) or "").strip()
                if c_name:
                    normalized.append({"id": c_id, "name": c_name})

        self.available_categories = normalized
        self.existing_categories = list(normalized)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

class GeminiConfig(BaseModel):
    """Configuration for Gemini provider.

    API key is read from GEMINI_API_KEY or GOOGLE_API_KEY environment variable if omitted.
    The key is masked in __repr__ to prevent accidental logging.
    """
    model_config = ConfigDict(extra="ignore")

    api_key: Optional[str] = None
    model_name: str = Field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    )
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_output_tokens: Optional[int] = 4096

    def get_effective_api_key(self) -> Optional[str]:
        """Resolves API key from config or environment variables, checking .env if needed."""
        key = (
            self.api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        if not key:
            try:
                from dotenv import load_dotenv
                load_dotenv()
                key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            except ImportError:
                pass
        return key

    def __repr__(self) -> str:
        key_status = "SET" if self.get_effective_api_key() else "UNSET"
        return f"GeminiConfig(model_name={self.model_name!r}, api_key=<{key_status}>, temperature={self.temperature})"


# ==============================================================================
# GEMINI WIRE DATA TRANSFER OBJECTS (Provider-Facing Fixed Schema)
# Decouples the wire schema sent to Google Gemini from the domain schema.
# Eliminates additionalProperties (dict) and Pydantic discriminated unions on the wire.
# ==============================================================================

class EvidenceSourceWire(BaseModel):
    """Provider-facing wire schema for evidence source."""
    model_config = ConfigDict(extra="ignore")
    type: str = Field(..., description="Source type: 'image', 'seller', or 'inferred'.")
    image_id: Optional[int] = Field(None, description="Numerical ID of image when source is 'image'.")


class EvidenceWire(BaseModel):
    """Provider-facing wire schema for field/attribute evidence."""
    model_config = ConfigDict(extra="ignore")
    source: EvidenceSourceWire = Field(..., description="Source of evidence.")
    explanation: str = Field(..., description="Detailed explanation of evidence.")


class TextFieldWire(BaseModel):
    """Provider-facing wire schema for canonical text fields."""
    model_config = ConfigDict(extra="ignore")
    type: str = Field(default="text", description="Field type, default 'text'.")
    value: Optional[str] = Field(None, description="Field string value, or null if unknown.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: EvidenceWire = Field(..., description="Mandatory evidence supporting this field.")


class CategoryValueWire(BaseModel):
    """Provider-facing wire schema for category classification values."""
    model_config = ConfigDict(extra="ignore")
    recommended_category_id: Optional[int] = Field(None, description="Matching category ID.")
    recommended_category_name: Optional[str] = Field(None, description="Matching category name.")
    proposed_category: Optional[str] = Field(None, description="Proposed subcategory name.")


class CategoryFieldWire(BaseModel):
    """Provider-facing wire schema for product category field."""
    model_config = ConfigDict(extra="ignore")
    value: Optional[CategoryValueWire] = Field(
        None,
        description="Category classification details. MUST NOT be null if product matches ANY category in the supplied platform taxonomy. Only null when no taxonomy category matches reliably."
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: EvidenceWire = Field(..., description="Mandatory evidence supporting category.")


class AttributeItemWire(BaseModel):
    """Provider-facing wire schema for an attribute item in the attributes array."""
    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., description="Name of the attribute (e.g. 'color', 'material', 'weight').")
    type: str = Field(default="text", description="Semantic attribute type: text, number, boolean, measurement, etc.")
    value: Optional[Any] = Field(None, description="Attribute value, or null if unknown.")
    unit: Optional[str] = Field(None, description="Unit of measurement if applicable.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: EvidenceWire = Field(..., description="Mandatory evidence supporting this attribute.")


class GeminiProductMetadataWire(BaseModel):
    """Provider-facing fixed structured output wire schema for Google Gemini.

    Uses an array of AttributeItemWire objects instead of a dynamic dictionary,
    guaranteeing full compatibility with Gemini Developer API without triggering additionalProperties.
    """
    model_config = ConfigDict(extra="ignore")
    title: TextFieldWire = Field(..., description="Suggested e-commerce product title.")
    description: TextFieldWire = Field(..., description="Product marketing and technical description.")
    brand: TextFieldWire = Field(..., description="Detected product brand.")
    category: CategoryFieldWire = Field(..., description="Category classification.")
    tags: list[str] = Field(default_factory=list, description="Categorical discovery tags.")
    keywords: list[str] = Field(default_factory=list, description="High-intent search keywords.")
    attributes: list[AttributeItemWire] = Field(default_factory=list, description="Array of structured attribute items.")


# ==============================================================================
# GEMINI PROVIDER
# ==============================================================================

class GeminiProvider:
    """Multimodal Gemini provider for structured product metadata generation."""

    def __init__(
        self,
        config: Optional[GeminiConfig] = None,
        client: Optional[Any] = None
    ):
        """Initializes the provider.

        Args:
            config: Optional GeminiConfig. If omitted, uses default settings and env vars.
            client: Optional injected Gemini client (useful for unit testing/mocking).
        """
        self.config = config or GeminiConfig()
        self._client = client

    def _get_client(self) -> Any:
        """Resolves or lazily instantiates the Gemini SDK client."""
        if self._client is not None:
            return self._client

        api_key = self.config.get_effective_api_key()
        if not api_key:
            raise GeminiConfigurationError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in environment or pass api_key in GeminiConfig."
            )

        # Use modern Google GenAI SDK (google-genai) as the single real SDK target
        try:
            from google import genai
            self._client = genai.Client(api_key=api_key)
            return self._client
        except ImportError:
            raise GeminiConfigurationError(
                "The 'google-genai' SDK is not installed in the environment. "
                "Please install 'google-genai' to make real API requests."
            )

    def build_system_prompt(self) -> str:
        """System instruction establishing AI product metadata extraction and strict grounding rules."""
        return (
            "You are an expert e-commerce catalog intelligence system producing structured product metadata.\n\n"
            "STRICT OPERATIONAL GUIDELINES:\n\n"
            "1. ROLE\n"
            "You are an e-commerce product intelligence system producing structured catalog metadata.\n\n"
            "2. OUTPUT CONFORMANCE\n"
            "Return ONLY a single valid JSON object strictly conforming to the GeminiProductMetadataWire contract.\n\n"
            "CRITICAL ROOT STRUCTURE: The JSON root object must contain these fields directly at the top level:\n"
            "- title\n"
            "- description\n"
            "- brand\n"
            "- category\n"
            "- tags\n"
            "- keywords\n"
            "- attributes\n\n"
            "Do NOT wrap the output in a top-level 'product_metadata', 'metadata', 'product', or other container key.\n"
            "Do not include markdown code fencing, commentary, or unverified keys.\n\n"
            "ATTRIBUTES FORMAT: attributes must be an array of objects. Each object must contain:\n"
            "name, type, value, unit, confidence, evidence.\n"
            "The application will convert this attribute array into its internal attribute dictionary.\n\n"
            "3. GROUNDING & EVIDENCE\n"
            "Every top-level field and attribute requires: value, confidence (0.0 to 1.0), and evidence.\n"
            "Explicitly distinguish between evidence source types:\n"
            "- 'image': Information directly supported by the supplied image (must include the exact image_id).\n"
            "- 'seller': Information explicitly supplied by seller/product context.\n"
            "- 'inferred': A genuine inference derived from available evidence.\n"
            "CRITICAL: Never represent inferred information as directly observed visual fact.\n\n"
            "4. UNKNOWN VALUES & NO GUESSING\n"
            "If information cannot be determined reliably from images or seller context:\n"
            "- set value = null\n"
            "- set confidence = 0.0\n"
            "- provide an evidence object explaining why it is unknown.\n"
            "Do not guess, extrapolate, or invent plausible values.\n\n"
            "5. IMAGE EVIDENCE PRIORITY\n"
            "For visually verifiable properties (e.g., color, pattern, form factor, visible materials, physical ports), "
            "images are primary evidence. Seller information is contextual evidence. Neither source is automatically infallible.\n\n"
            "6. CONFLICT RESOLUTION\n"
            "- Seller vs Image: When seller claims and image evidence conflict, prefer strong, clearly observable visual "
            "evidence for visually verifiable properties. Preserve seller information only when the property cannot be visually verified. "
            "Expose uncertainty through lower confidence and explanatory evidence when the conflict cannot be reliably resolved.\n"
            "- Multiple Images: When multiple images appear to conflict, determine whether the difference represents a legitimate "
            "product variant (e.g. alternate colors, bundled accessories, multiple angles) or genuine contradiction. If there is a strong "
            "hierarchical or physical explanation, resolve it; otherwise preserve uncertainty rather than inventing a resolution.\n\n"
            "7. EXACT IMAGE IDENTITY\n"
            "When citing 'image' evidence, you MUST cite the exact supplied numerical image_id. Never invent or hallucinate image IDs.\n\n"
            "8. CATEGORY TAXONOMY MATCHING & CATEGORY OUTPUT REQUIREMENT\n"
            "- The available platform taxonomy categories are provided as a list of objects, each containing an authoritative database ID ('id') and name ('name').\n"
            "- Match the product against the platform's existing category taxonomy.\n"
            "- MANDATORY CATEGORY VALUE RULE:\n"
            "  If the product matches ANY category in the supplied platform taxonomy:\n"
            "  * category.value MUST NOT be null.\n"
            "  * Set recommended_category_id to the exact id from the matching taxonomy item.\n"
            "  * Set recommended_category_name to the exact name from the matching taxonomy item.\n"
            "  * Do not put this information only in evidence.\n"
            "  * Do not use inferred evidence as a substitute for the category value.\n"
            "- Example:\n"
            "  If taxonomy contains {\"id\": 3, \"name\": \"Shoes\"} and the product is a shoe:\n"
            "  category: {\n"
            "    \"value\": {\n"
            "      \"recommended_category_id\": 3,\n"
            "      \"recommended_category_name\": \"Shoes\",\n"
            "      \"proposed_category\": null\n"
            "    },\n"
            "    \"confidence\": 1.0,\n"
            "    \"evidence\": {\"source\": {\"type\": \"image\", \"image_id\": 1}, \"explanation\": \"Visual inspection confirms athletic shoes.\"}\n"
            "  }\n"
            "- If the existing taxonomy is too broad (e.g. 'Shoes'), provide the matching existing category (with its ID and name) AND propose a specific subcategory in 'proposed_category' (e.g. 'Sneakers').\n"
            "- ONLY use category.value = null when no supplied taxonomy category can be matched reliably.\n"
            "- Never invent, hallucinate, or guess a category ID that is not in the supplied taxonomy.\n\n"
            "9. SEMANTIC STRUCTURED ATTRIBUTES\n"
            "Catalog attributes must use structured semantic types where appropriate:\n"
            "- text: plain descriptive values.\n"
            "- number: numeric metrics.\n"
            "- boolean: binary features (e.g. waterproof, wireless).\n"
            "- measurement: value + unit (e.g. weight, volume, battery capacity).\n"
            "- range: min_value + max_value + unit (e.g. operating temperature, adjustable height).\n"
            "- dimensions: length + width + height + unit.\n"
            "- array: homogeneous list of typed values.\n"
            "- object: structured key-value maps.\n"
            "Use measurement, range, and dimensions structures whenever physical quantities are identified.\n\n"
            "10. TAGS VS KEYWORDS\n"
            "- Tags: Descriptive, authoritative catalog tags representing core features and taxonomy.\n"
            "- Keywords: High-intent search and retrieval phrases. Keywords are non-authoritative search helpers and "
            "must never be treated as canonical product facts.\n\n"
            "11. PRODUCT VARIANTS\n"
            "If images suggest legitimate product variants (e.g. multiple colors, editions, pack sizes):\n"
            "- identify them in the metadata draft where the schema permits (e.g. in description or attributes).\n"
            "- do not create ProductVariant records or invent database entity IDs.\n"
            "- do not assume differences are contradictions without evidence.\n\n"
            "12. IMAGE ROLES\n"
            "If the system provides seller image-role information (e.g. front, back, packaging, nutrition_label):\n"
            "- use it as helpful context for where to locate specific information.\n"
            "- distinguish seller-provided role information from AI inference.\n"
            "- do not invent persistent database role fields.\n\n"
            "13. NO IMAGES BEHAVIOR\n"
            "If no product images are provided:\n"
            "- generation is still permitted using seller context alone.\n"
            "- clearly reduce confidence scores for all visually dependent attributes.\n"
            "- do NOT claim visual evidence or cite image sources when no images exist.\n\n"
            "14. SELLER CLAIMS\n"
            "Do not convert unsupported seller claims (e.g. 'world's best', 'military grade', unverified specs) into visual facts.\n\n"
            "15. ANTI-HALLUCINATION SAFEGUARDS\n"
            "Never invent: brand, material, dimensions, specifications, certifications, compatibility, model numbers, "
            "safety claims, or performance claims unless directly corroborated by the provided images or seller context.\n\n"
            "16. INTERNAL CONSISTENCY\n"
            "Ensure the product receives internally consistent metadata across all fields (e.g., title, description, category, "
            "attributes, and tags must align). Avoid contradictory statements unless the evidence demonstrates a genuine variant or conflict."
        )

    def build_multimodal_request(self, context: AIProductContext) -> dict[str, Any]:
        """Constructs the prompt and contents parts for the multimodal request.

        Preserves image identities (image_id), MIME types, display order,
        and integrates seller context and category taxonomy.
        """
        prompt_parts: list[str] = [
            f"--- PRODUCT CONTEXT (Product ID: {context.product_id}) ---"
        ]

        if context.title:
            prompt_parts.append(f"Seller Title: {context.title}")
        if context.description:
            prompt_parts.append(f"Seller Description: {context.description}")
        if context.brand:
            prompt_parts.append(f"Seller Brand: {context.brand}")
        if context.price is not None:
            prompt_parts.append(f"Product Price: {context.price}")
        if context.current_category or context.category_hint:
            cat_val = context.current_category or context.category_hint
            prompt_parts.append(f"Current Category / Hint: {cat_val}")

        categories = context.available_categories or context.existing_categories
        if categories:
            cat_list: list[dict[str, Any]] = []
            for c in categories:
                if isinstance(c, dict):
                    cat_list.append({"id": c.get("id"), "name": c.get("name") or ""})
                else:
                    cat_list.append({"id": getattr(c, "id", None), "name": getattr(c, "name", str(c))})
            prompt_parts.append(f"Available Platform Taxonomy Categories: {json.dumps(cat_list)}")

        prompt_parts.append("\n--- PRODUCT IMAGES ---")
        prompt_parts.append(f"Total images provided: {len(context.images)}")

        image_items: list[dict[str, Any]] = []
        if context.images:
            prompt_parts.append(
                "NOTE ON IMAGE EVIDENCE: Each image below is uniquely identified by its exact image_id. "
                "When citing visual evidence in your output, you MUST reference the exact image_id."
            )
            for idx, img in enumerate(context.images, start=1):
                order_info = f", display_order={img.display_order}" if img.display_order is not None else ""
                role_info = f", seller_role='{img.role}'" if img.role else ""
                prompt_parts.append(
                    f"Image #{idx}: image_id={img.image_id}{order_info}, mime_type='{img.mime_type}'{role_info}"
                )
                image_items.append({
                    "image_id": img.image_id,
                    "mime_type": img.mime_type,
                    "bytes": img.get_bytes(),
                })
        else:
            prompt_parts.append("No product images provided. Analyze based on seller context alone.")

        user_text = "\n".join(prompt_parts)
        return {
            "system_instruction": self.build_system_prompt(),
            "user_text": user_text,
            "images": image_items,
        }

    def generate_product_metadata(self, context: AIProductContext) -> AIProductMetadata:
        """Sends the multimodal context to Gemini and returns validated AIProductMetadata.

        Args:
            context: AIProductContext containing product details and images.

        Returns:
            Validated AIProductMetadata instance.

        Raises:
            GeminiConfigurationError: If API key or SDK is missing.
            GeminiResponseValidationError: If Gemini output violates AIProductMetadata schema.
            GeminiAPIError: If the Gemini API call fails.
        """
        client = self._get_client()
        request_payload = self.build_multimodal_request(context)

        raw_response = self._execute_generate_content(client, request_payload)
        return self._parse_and_validate_response(raw_response)

    def _execute_generate_content(self, client: Any, request_payload: dict[str, Any]) -> Any:
        """Executes content generation via the modern Google GenAI SDK or injected mock client."""
        try:
            # 1. Real Google GenAI SDK client path: client.models.generate_content(...)
            if hasattr(client, "models") and hasattr(client.models, "generate_content") and not hasattr(client, "generate_content"):
                try:
                    from google.genai import types
                    contents: list[Any] = [request_payload["user_text"]]
                    for img in request_payload["images"]:
                        contents.append(
                            types.Part.from_bytes(data=img["bytes"], mime_type=img["mime_type"])
                        )

                    try:
                        config = types.GenerateContentConfig(
                            system_instruction=request_payload["system_instruction"],
                            temperature=self.config.temperature,
                            max_output_tokens=self.config.max_output_tokens,
                            response_mime_type="application/json",
                            response_schema=GeminiProductMetadataWire,
                        )
                        return client.models.generate_content(
                            model=self.config.model_name,
                            contents=contents,
                            config=config,
                        )
                    except ValueError as ve:
                        # Defensive fallback only if SDK/API cannot serialize schema
                        if "schema" in str(ve).lower() or "additionalproperties" in str(ve).lower():
                            fallback_config = types.GenerateContentConfig(
                                system_instruction=request_payload["system_instruction"],
                                temperature=self.config.temperature,
                                max_output_tokens=self.config.max_output_tokens,
                                response_mime_type="application/json",
                            )
                            return client.models.generate_content(
                                model=self.config.model_name,
                                contents=contents,
                                config=fallback_config,
                            )
                        raise
                except ImportError:
                    # Injected mock where models.generate_content is used without google-genai installed
                    return client.models.generate_content(
                        model=self.config.model_name,
                        contents=[request_payload["user_text"]],
                        config=request_payload,
                    )

            # 2. Injected mock/test client with direct generate_content(...)
            elif hasattr(client, "generate_content"):
                return client.generate_content(
                    model=self.config.model_name,
                    system_instruction=request_payload["system_instruction"],
                    user_text=request_payload["user_text"],
                    images=request_payload["images"],
                    response_schema=GeminiProductMetadataWire,
                )

            # 3. Direct callable mock
            elif callable(client):
                return client(request_payload)

            else:
                raise GeminiConfigurationError(
                    f"Unsupported Gemini client object: {type(client)}. Client must support "
                    "'models.generate_content' (modern google-genai SDK) or 'generate_content' (mock)."
                )

        except (GeminiConfigurationError, GeminiResponseValidationError):
            raise
        except Exception as e:
            raise GeminiAPIError(f"Gemini API generation call failed: {e}") from e

    @staticmethod
    def _evidence_wire_to_dict(ev: EvidenceWire) -> dict[str, Any]:
        """Converts an EvidenceWire DTO into the dictionary structure expected by Evidence model."""
        source_dict: dict[str, Any] = {"type": ev.source.type}
        if ev.source.type == "image" and ev.source.image_id is not None:
            source_dict["image_id"] = ev.source.image_id
        return {
            "source": source_dict,
            "explanation": ev.explanation,
        }

    def _wire_to_domain_metadata(self, wire: GeminiProductMetadataWire) -> AIProductMetadata:
        """Transforms a GeminiProductMetadataWire DTO into the canonical AIProductMetadata domain model.

        Converts the wire attribute array [AttributeItemWire] into the domain attribute
        dictionary dict[str, AttributeField] keyed by attribute name.
        Preserves exact confidence scores, evidence objects, and types.
        """
        cat_val = None
        if wire.category.value:
            cat_val = wire.category.value.model_dump()

        domain_dict: dict[str, Any] = {
            "title": {
                "type": wire.title.type or "text",
                "value": wire.title.value,
                "confidence": wire.title.confidence,
                "evidence": self._evidence_wire_to_dict(wire.title.evidence),
            },
            "description": {
                "type": wire.description.type or "text",
                "value": wire.description.value,
                "confidence": wire.description.confidence,
                "evidence": self._evidence_wire_to_dict(wire.description.evidence),
            },
            "brand": {
                "type": wire.brand.type or "text",
                "value": wire.brand.value,
                "confidence": wire.brand.confidence,
                "evidence": self._evidence_wire_to_dict(wire.brand.evidence),
            },
            "category": {
                "value": cat_val,
                "confidence": wire.category.confidence,
                "evidence": self._evidence_wire_to_dict(wire.category.evidence),
            },
            "tags": wire.tags,
            "keywords": wire.keywords,
            "attributes": {},
        }

        for attr in wire.attributes:
            attr_dict: dict[str, Any] = {
                "type": attr.type,
                "value": attr.value,
                "confidence": attr.confidence,
                "evidence": self._evidence_wire_to_dict(attr.evidence),
            }
            if attr.unit is not None:
                attr_dict["unit"] = attr.unit
            domain_dict["attributes"][attr.name] = attr_dict

        try:
            return AIProductMetadata.model_validate(domain_dict)
        except ValidationError as e:
            raise GeminiResponseValidationError(
                f"Transformed Gemini wire output failed validation against AIProductMetadata contract: {e}"
            ) from e

    def _parse_and_validate_response(self, raw_response: Any) -> AIProductMetadata:
        """Parses model output and validates against AIProductMetadata schema."""
        # 1. Direct AIProductMetadata instance
        if isinstance(raw_response, AIProductMetadata):
            return raw_response

        # 2. Direct GeminiProductMetadataWire instance
        if isinstance(raw_response, GeminiProductMetadataWire):
            return self._wire_to_domain_metadata(raw_response)

        data_to_validate: Any = None

        # 3. Response object with parsed attribute (typed object mode)
        if hasattr(raw_response, "parsed"):
            parsed_val = raw_response.parsed
            if isinstance(parsed_val, AIProductMetadata):
                return parsed_val
            elif isinstance(parsed_val, GeminiProductMetadataWire):
                return self._wire_to_domain_metadata(parsed_val)
            elif isinstance(parsed_val, dict):
                data_to_validate = parsed_val

        # 4. Response object with text property (most common Gemini SDK response)
        if data_to_validate is None and hasattr(raw_response, "text") and isinstance(raw_response.text, str):
            text = raw_response.text.strip()
            # Strip markdown code fencing if returned by model
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            try:
                data_to_validate = json.loads(text)
            except json.JSONDecodeError as e:
                raise GeminiResponseValidationError(f"Failed to parse Gemini response as JSON: {e}") from e

        # 5. Raw dictionary
        elif data_to_validate is None and isinstance(raw_response, dict):
            data_to_validate = raw_response

        # 6. Raw string
        elif data_to_validate is None and isinstance(raw_response, str):
            try:
                data_to_validate = json.loads(raw_response)
            except json.JSONDecodeError as e:
                raise GeminiResponseValidationError(f"Failed to parse string response as JSON: {e}") from e

        elif data_to_validate is None:
            raise GeminiResponseValidationError(
                f"Unrecognized response format from Gemini provider: {type(raw_response)}"
            )

        # Defensive normalization for known container wrappers (e.g. {"product_metadata": {...}})
        if isinstance(data_to_validate, dict) and "title" not in data_to_validate:
            for wrapper_key in ("product_metadata", "metadata", "product", "data"):
                inner = data_to_validate.get(wrapper_key)
                if isinstance(inner, dict) and any(
                    key in inner
                    for key in ("title", "description", "brand", "category")
                ):
                    data_to_validate = inner
                    break

        if not isinstance(data_to_validate, dict):
            raise GeminiResponseValidationError(
                f"Expected JSON object response from Gemini, got {type(data_to_validate)}"
            )

        # Check if payload is in GeminiProductMetadataWire format (attributes is an array/list)
        if isinstance(data_to_validate.get("attributes"), list):
            try:
                wire = GeminiProductMetadataWire.model_validate(data_to_validate)
            except ValidationError as e:
                raise GeminiResponseValidationError(
                    f"Gemini output failed validation against GeminiProductMetadataWire contract: {e}"
                ) from e
            return self._wire_to_domain_metadata(wire)

        # Otherwise validate directly through Pydantic AIProductMetadata contract (for domain-dict mock payloads)
        try:
            return AIProductMetadata.model_validate(data_to_validate)
        except ValidationError as e:
            raise GeminiResponseValidationError(
                f"Gemini output failed validation against AIProductMetadata contract: {e}"
            ) from e
