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
    existing_categories: list[str] = field(default_factory=list)
    available_categories: list[str] = field(default_factory=list)
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
    model_name: str = "gemini-2.5-flash"
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
            "Return ONLY data strictly conforming to the supplied AIProductMetadata JSON schema. "
            "Do not include markdown wrappers, conversational commentary, or unverified keys.\n\n"
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
            "8. CATEGORY TAXONOMY MATCHING\n"
            "- Match the product against the platform's existing category taxonomy.\n"
            "- Recommend the best matching existing category when appropriate.\n"
            "- If the existing taxonomy is too broad, propose a more specific subcategory in proposed_category.\n"
            "- Do NOT mutate the taxonomy.\n"
            "- Do NOT invent an existing category ID that was not provided.\n\n"
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
            cat_list = ", ".join(f'"{c}"' for c in categories)
            prompt_parts.append(f"Available Platform Taxonomy Categories: [{cat_list}]")

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
                            response_schema=AIProductMetadata,
                        )
                        return client.models.generate_content(
                            model=self.config.model_name,
                            contents=contents,
                            config=config,
                        )
                    except ValueError as ve:
                        if "additionalProperties" in str(ve):
                            # Developer API mode does not support additionalProperties in response_schema.
                            # Fall back to structured JSON output with prompt-grounded schema.
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
                    response_schema=AIProductMetadata,
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

    def _parse_and_validate_response(self, raw_response: Any) -> AIProductMetadata:
        """Parses model output and validates against AIProductMetadata schema."""
        data_to_validate: Any = None

        # 1. Direct AIProductMetadata instance
        if isinstance(raw_response, AIProductMetadata):
            return raw_response

        # 2. Response object with text property (most common Gemini SDK response)
        if hasattr(raw_response, "text") and isinstance(raw_response.text, str):
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

        # 3. Response object with parsed attribute (typed object mode)
        elif hasattr(raw_response, "parsed") and isinstance(raw_response.parsed, (dict, AIProductMetadata)):
            data_to_validate = raw_response.parsed

        # 4. Raw dictionary
        elif isinstance(raw_response, dict):
            data_to_validate = raw_response

        # 5. Raw string
        elif isinstance(raw_response, str):
            try:
                data_to_validate = json.loads(raw_response)
            except json.JSONDecodeError as e:
                raise GeminiResponseValidationError(f"Failed to parse string response as JSON: {e}") from e

        else:
            raise GeminiResponseValidationError(
                f"Unrecognized response format from Gemini provider: {type(raw_response)}"
            )

        # Validate through Pydantic AIProductMetadata contract
        try:
            return AIProductMetadata.model_validate(data_to_validate)
        except ValidationError as e:
            raise GeminiResponseValidationError(
                f"Gemini output failed validation against AIProductMetadata contract: {e}"
            ) from e
