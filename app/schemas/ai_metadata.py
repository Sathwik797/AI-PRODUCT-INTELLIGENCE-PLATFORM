"""AI Product Metadata Pydantic Contract.

Phase 05 – Step 2: AI Product Intelligence Platform.

This module defines the strict, strongly-typed JSON schema contract for AI-generated
product metadata. It establishes the structured data representation used by multimodal
vision models (e.g. Gemini Vision) to return product titles, descriptions, brands,
dual-category classifications, retrieval keywords, and extensible typed attributes.

Key Architectural Decisions:
1. Unknown Values Allowed (value=null):
   When multimodal AI cannot reliably extract or verify an attribute from visual
   evidence or seller inputs (e.g. battery chemistry not visible in exterior photos),
   it must return `value = None` with a low or 0.0 confidence score and provide
   explanatory evidence. This prevents hallucinations while explicitly recording that
   the attribute was analyzed.

2. Evidence is Mandatory:
   Every field and dynamic attribute requires structured evidence citing its source
   (e.g., an exact image_id or seller input) and an explanation. This ensures
   accountability, explainability, and informed human-in-the-loop review before AI drafts
   are merged into canonical product catalog tables.

3. Simple Tags and Keywords:
   `tags` and `keywords` are modeled as simple `list[str]` because they serve search
   indexing, faceted filtering, and dense vector embeddings rather than standalone
   verifiable factual claims. Requiring evidence on individual keywords would introduce
   massive token overhead with zero business value.

4. Bounded Recursive Depth (Maximum 2):
   Arrays and Objects can contain nested typed values up to a maximum container
   depth of 2 (e.g. an array of objects or an object of arrays). Unbounded recursion
   is strictly prohibited to prevent runaway JSON complexity and maintain full
   compatibility with LLM structured output decoders such as Gemini `response_schema`.
"""

from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)


# ==============================================================================
# EVIDENCE & SOURCE MODELS
# ==============================================================================

class ImageEvidenceSource(BaseModel):
    """Evidence grounded directly in a specific uploaded product image."""
    model_config = ConfigDict(extra="forbid")

    type: Literal["image"] = "image"
    image_id: int = Field(
        ...,
        description="ID of the specific product image from which evidence was observed."
    )


class SellerEvidenceSource(BaseModel):
    """Evidence provided by seller specifications or catalog input."""
    model_config = ConfigDict(extra="forbid")

    type: Literal["seller"] = "seller"


class InferredEvidenceSource(BaseModel):
    """Evidence logically deduced from standard product domain norms or combined signals."""
    model_config = ConfigDict(extra="forbid")

    type: Literal["inferred"] = "inferred"


# Discriminated union for controlled, verifiable evidence sources
EvidenceSource = Annotated[
    Union[ImageEvidenceSource, SellerEvidenceSource, InferredEvidenceSource],
    Field(discriminator="type")
]


class Evidence(BaseModel):
    """Structured evidence justifying an AI extraction or classification."""
    source: EvidenceSource = Field(
        ...,
        description="Hierarchical source reference identifying where the evidence originated."
    )
    explanation: str = Field(
        ...,
        min_length=1,
        description="Reasoning or description explaining how the evidence supports the field value."
    )


# ==============================================================================
# STRUCTURED VALUE CONTAINERS (Range & Dimensions)
# ==============================================================================

class RangeValue(BaseModel):
    """Structured representation of a numerical range."""
    min: float = Field(..., description="Minimum value in range.")
    max: float = Field(..., description="Maximum value in range.")

    @model_validator(mode="after")
    def validate_min_max(self) -> "RangeValue":
        if self.min > self.max:
            raise ValueError("Range minimum value cannot be greater than maximum value.")
        return self


class DimensionsValue(BaseModel):
    """Structured 3D dimensions of an item."""
    length: float = Field(..., ge=0.0, description="Length measurement (>= 0).")
    width: float = Field(..., ge=0.0, description="Width measurement (>= 0).")
    height: float = Field(..., ge=0.0, description="Height measurement (>= 0).")


# ==============================================================================
# RECURSIVE DEPTH CALCULATION UTILITY
# ==============================================================================

def get_node_depth(node: Any) -> int:
    """Computes container nesting depth for arrays and objects.

    Leaf nodes (text, number, boolean, measurement, range, dimensions) have container depth 0.
    ArrayNode and ObjectNode containers have depth 1 + max(child container depths, default=0).
    """
    if isinstance(node, (ArrayNode,)):
        if not node.value:
            return 1
        return 1 + max(get_node_depth(item) for item in node.value)
    elif isinstance(node, (ObjectNode,)):
        if not node.value:
            return 1
        return 1 + max(get_node_depth(item) for item in node.value.values())
    elif isinstance(node, dict):
        node_type = node.get("type")
        if node_type == "array":
            items = node.get("value") or []
            if not items:
                return 1
            return 1 + max(get_node_depth(item) for item in items)
        elif node_type == "object":
            items = node.get("value") or {}
            if not items:
                return 1
            return 1 + max(get_node_depth(item) for item in items.values())
    return 0


# ==============================================================================
# BASE TYPED NODES (Leaves & Recursive Containers)
# Nested TypedNodes represent typed values and structure only (no confidence/evidence).
# Confidence and evidence are required on top-level Field models.
# ==============================================================================

class TextNode(BaseModel):
    """Semantic text attribute value."""
    type: Literal["text"] = "text"
    value: Optional[StrictStr] = Field(None, description="String value, or null if unknown.")


class NumberNode(BaseModel):
    """Semantic numeric attribute value."""
    type: Literal["number"] = "number"
    value: Optional[Union[StrictInt, StrictFloat]] = Field(None, description="Numeric value, or null if unknown.")


class BooleanNode(BaseModel):
    """Semantic boolean flag value."""
    type: Literal["boolean"] = "boolean"
    value: Optional[StrictBool] = Field(None, description="Boolean flag, or null if unknown.")


class MeasurementNode(BaseModel):
    """Semantic physical measurement with magnitude and unit."""
    type: Literal["measurement"] = "measurement"
    value: Optional[Union[StrictInt, StrictFloat]] = Field(None, description="Measurement magnitude, or null if unknown.")
    unit: Optional[str] = Field(None, description="Unit of measurement (e.g. 'kg', 'ml', 'watts').")

    @model_validator(mode="after")
    def validate_measurement_unit(self) -> "MeasurementNode":
        if self.value is not None and (self.unit is None or not self.unit.strip()):
            raise ValueError("Unit is required when measurement value is provided.")
        return self


class RangeNode(BaseModel):
    """Semantic numerical range with unit."""
    type: Literal["range"] = "range"
    value: Optional[RangeValue] = Field(None, description="Min/max range bounds, or null if unknown.")
    unit: Optional[str] = Field(None, description="Unit of range (e.g. '°C', 'Hz', 'V').")

    @model_validator(mode="after")
    def validate_range_unit(self) -> "RangeNode":
        if self.value is not None and (self.unit is None or not self.unit.strip()):
            raise ValueError("Unit is required when range value is provided.")
        return self


class DimensionsNode(BaseModel):
    """Semantic 3D spatial dimensions with unit."""
    type: Literal["dimensions"] = "dimensions"
    value: Optional[DimensionsValue] = Field(None, description="Length/width/height dimensions, or null if unknown.")
    unit: Optional[str] = Field(None, description="Unit of length (e.g. 'cm', 'in', 'mm').")

    @model_validator(mode="after")
    def validate_dimensions_unit(self) -> "DimensionsNode":
        if self.value is not None and (self.unit is None or not self.unit.strip()):
            raise ValueError("Unit is required when dimensions value is provided.")
        return self


class ArrayNode(BaseModel):
    """Typed list of semantic nodes with maximum container depth of 2."""
    type: Literal["array"] = "array"
    value: Optional[list["TypedNode"]] = Field(None, description="List of typed values, or null if unknown.")

    @model_validator(mode="after")
    def validate_depth(self) -> "ArrayNode":
        depth = get_node_depth(self)
        if depth > 2:
            raise ValueError(f"Recursive nesting depth ({depth}) exceeds maximum allowed depth of 2.")
        return self


class ObjectNode(BaseModel):
    """Typed dictionary of semantic nodes with maximum container depth of 2."""
    type: Literal["object"] = "object"
    value: Optional[dict[str, "TypedNode"]] = Field(None, description="Map of string keys to typed values, or null if unknown.")

    @model_validator(mode="after")
    def validate_depth(self) -> "ObjectNode":
        depth = get_node_depth(self)
        if depth > 2:
            raise ValueError(f"Recursive nesting depth ({depth}) exceeds maximum allowed depth of 2.")
        return self


# Discriminated union for arbitrary recursive typed nodes
TypedNode = Annotated[
    Union[
        TextNode,
        NumberNode,
        BooleanNode,
        MeasurementNode,
        RangeNode,
        DimensionsNode,
        ArrayNode,
        ObjectNode,
    ],
    Field(discriminator="type")
]

# Rebuild models to resolve recursive type references in Pydantic V2
ArrayNode.model_rebuild()
ObjectNode.model_rebuild()


# ==============================================================================
# PRIMARY AI ATTRIBUTE FIELDS (Top-Level Attributes)
# Top-level fields require strict confidence and evidence.
# ==============================================================================

class TextField(TextNode):
    """Top-level text field with mandatory confidence and evidence."""
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: Evidence = Field(..., description="Mandatory evidence supporting this field.")


class NumberField(NumberNode):
    """Top-level number field with mandatory confidence and evidence."""
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: Evidence = Field(..., description="Mandatory evidence supporting this field.")


class BooleanField(BooleanNode):
    """Top-level boolean field with mandatory confidence and evidence."""
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: Evidence = Field(..., description="Mandatory evidence supporting this field.")


class MeasurementField(MeasurementNode):
    """Top-level measurement field with mandatory confidence and evidence."""
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: Evidence = Field(..., description="Mandatory evidence supporting this field.")


class RangeField(RangeNode):
    """Top-level range field with mandatory confidence and evidence."""
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: Evidence = Field(..., description="Mandatory evidence supporting this field.")


class DimensionsField(DimensionsNode):
    """Top-level dimensions field with mandatory confidence and evidence."""
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: Evidence = Field(..., description="Mandatory evidence supporting this field.")


class ArrayField(ArrayNode):
    """Top-level array attribute with mandatory confidence and evidence."""
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: Evidence = Field(..., description="Mandatory evidence supporting this field.")


class ObjectField(ObjectNode):
    """Top-level object attribute with mandatory confidence and evidence."""
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0, 1.0].")
    evidence: Evidence = Field(..., description="Mandatory evidence supporting this field.")


# Discriminated union of top-level attribute fields
AttributeField = Annotated[
    Union[
        TextField,
        NumberField,
        BooleanField,
        MeasurementField,
        RangeField,
        DimensionsField,
        ArrayField,
        ObjectField,
    ],
    Field(discriminator="type")
]


# ==============================================================================
# CATEGORY CLASSIFICATION CONTRACT
# ==============================================================================

class CategoryRecommendationValue(BaseModel):
    """Dual category classification outcome.

    Preserves platform taxonomy integrity by separating matches to existing categories
    from newly suggested or more specific subcategory proposals.
    """
    recommended_category_id: Optional[int] = Field(
        None,
        description="ID of the matching category in the existing database taxonomy."
    )
    recommended_category_name: Optional[str] = Field(
        None,
        description="Name of the matching category in the existing database taxonomy."
    )
    proposed_category: Optional[str] = Field(
        None,
        description="Proposed more specific subcategory name if existing taxonomy is too broad."
    )


class CategoryField(BaseModel):
    """Category field recommendation with confidence and mandatory evidence."""
    value: Optional[CategoryRecommendationValue] = Field(
        None,
        description="Recommended existing and/or proposed categories, or null if unknown."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score [0.0, 1.0]."
    )
    evidence: Evidence = Field(
        ...,
        description="Mandatory evidence justifying this category classification."
    )

    @model_validator(mode="after")
    def validate_category_content(self) -> "CategoryField":
        if self.value is not None:
            if (
                self.value.recommended_category_id is None
                and (self.value.recommended_category_name is None or not self.value.recommended_category_name.strip())
                and (self.value.proposed_category is None or not self.value.proposed_category.strip())
            ):
                raise ValueError(
                    "Category value, when provided, must specify at least one of: "
                    "recommended_category_id, recommended_category_name, or proposed_category."
                )
        return self


# ==============================================================================
# SELLER ACCEPTANCE ENUM
# ==============================================================================

class FieldAcceptanceStatus(str, Enum):
    """Lifecycle state of seller approval for an AI-generated field."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    MODIFIED = "modified"
    REJECTED = "rejected"


# ==============================================================================
# TOP-LEVEL COMPLETE CONTRACT
# ==============================================================================

class AIProductMetadata(BaseModel):
    """Complete multimodal AI product metadata output contract.

    Aggregates core e-commerce canonical suggestions (title, description, brand,
    category), discovery keywords/tags, and an extensible dictionary of typed
    product attributes (materials, performance specs, dimensions, etc.).
    """
    title: TextField = Field(
        ...,
        description="Suggested e-commerce product title with confidence and evidence."
    )
    description: TextField = Field(
        ...,
        description="Detailed product marketing and technical description with confidence and evidence."
    )
    brand: TextField = Field(
        ...,
        description="Detected product brand with confidence and evidence."
    )
    category: CategoryField = Field(
        ...,
        description="Dual category classification (existing match + proposed subcategory)."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Simple list of categorical discovery tags."
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Simple list of high-intent search and SEO keywords."
    )
    attributes: dict[str, AttributeField] = Field(
        default_factory=dict,
        description="Extensible key-value map of typed attributes (e.g. material, weight, color)."
    )
