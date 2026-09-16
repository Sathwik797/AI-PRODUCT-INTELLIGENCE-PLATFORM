"""Deterministic Embedding Text Builder & Content Hasher.

Phase 06: Implements Q34, Q35, Q36, Q38.
Compiles a deterministic, hybrid labeled + normalized semantic document from canonical
product data and accepted AI metadata. Strictly excludes operational fields, IDs, price,
stock, unaccepted suggestions, confidence, and evidence.
"""

import hashlib
import re
from typing import Any, Optional


BUILDER_VERSION: str = "v1"


def normalize_whitespace(text: str) -> str:
    """Collapses consecutive whitespace and trims ends."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def compute_content_hash(text: str) -> str:
    """Computes deterministic SHA-256 hex digest of the canonical embedding text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingTextBuilder:
    """Compiles canonical product data and accepted AI metadata into a deterministic embedding document.

    Follows fixed semantic section order:
    1. Title: <title>
    2. Brand: <brand>
    3. Category: <category_name>
    4. Description: <description>
    5. Attributes: <key>: <formatted_value>; ...
    6. Tags: <tag1>, <tag2>, ...
    7. Keywords: <kw1>, <kw2>, ...
    """

    @classmethod
    def format_attribute_value(cls, val: Any) -> str:
        """Formats an attribute value deterministically based on its semantic type."""
        if val is None:
            return ""

        # If it's a dict representation (such as an AttributeField or TypedNode)
        if isinstance(val, dict):
            # If wrapped in an AttributeField structure (which has confidence/evidence)
            if ("confidence" in val or "evidence" in val) and "value" in val:
                val = val["value"]
            if val is None:
                return ""

            if isinstance(val, dict):
                node_type = val.get("type")
                node_val = val.get("value")

                if node_type == "text":
                    return normalize_whitespace(str(node_val))
                elif node_type == "number":
                    return str(node_val)
                elif node_type == "boolean":
                    return "true" if node_val else "false"
                elif node_type == "measurement":
                    unit = val.get("unit", "")
                    return f"{node_val} {unit}".strip()
                elif node_type == "range":
                    # RangeValue min / max
                    r_min = val.get("min")
                    r_max = val.get("max")
                    return f"{r_min} - {r_max}"
                elif node_type == "dimensions":
                    # DimensionsValue length / width / height - preserve meaningful L x W x H order
                    length = val.get("length", 0)
                    width = val.get("width", 0)
                    height = val.get("height", 0)
                    return f"L: {length} x W: {width} x H: {height}"
                elif node_type == "array":
                    items = [cls.format_attribute_value(item) for item in (node_val or [])]
                    clean_items = sorted(set(filter(None, items)))
                    return ", ".join(clean_items)
                elif node_type == "object":
                    items_dict = node_val or {}
                    parts = []
                    for k in sorted(items_dict.keys()):
                        formatted_sub = cls.format_attribute_value(items_dict[k])
                        if formatted_sub:
                            parts.append(f"{k}: {formatted_sub}")
                    return "; ".join(parts)
                else:
                    # Fallback for plain dictionary
                    parts = []
                    for k in sorted(val.keys()):
                        formatted_sub = cls.format_attribute_value(val[k])
                        if formatted_sub:
                            parts.append(f"{k}: {formatted_sub}")
                    return "; ".join(parts)

        # If it's a list or set
        if isinstance(val, (list, set, tuple)):
            formatted_items = [cls.format_attribute_value(item) for item in val]
            clean_items = sorted(set(filter(None, formatted_items)))
            return ", ".join(clean_items)

        # If it's a bool
        if isinstance(val, bool):
            return "true" if val else "false"

        # Scalars (str, int, float)
        return normalize_whitespace(str(val))

    @classmethod
    def build(
        cls,
        product: Any,
        accepted_metadata: Optional[dict[str, Any]] = None,
        category_name: Optional[str] = None
    ) -> str:
        """Constructs the deterministic embedding document text.

        Args:
            product: Product model instance or duck-typed object.
            accepted_metadata: Optional dict containing accepted/modified AI fields:
                               e.g. {"tags": [...], "keywords": [...], "attributes": {...}}
            category_name: Optional category name string if not eager-loaded on product.category.

        Returns:
            Normalized deterministic text string.
        """
        sections: list[str] = []

        # 1. Title (Canonical)
        title = normalize_whitespace(getattr(product, "title", "") or "")
        if title:
            sections.append(f"Title: {title}")

        # 2. Brand (Canonical)
        brand = normalize_whitespace(getattr(product, "brand", "") or "")
        if brand:
            sections.append(f"Brand: {brand}")

        # 3. Category (Canonical)
        cat_name = category_name
        if not cat_name and hasattr(product, "category") and product.category is not None:
            cat_name = getattr(product.category, "name", None)
        cat_name = normalize_whitespace(cat_name or "")
        if cat_name:
            sections.append(f"Category: {cat_name}")

        # 4. Description (Canonical)
        desc = normalize_whitespace(getattr(product, "description", "") or "")
        if desc:
            sections.append(f"Description: {desc}")

        # Accepted AI Metadata (Non-canonical discovery attributes)
        ai_data = accepted_metadata or {}

        # 5. Attributes (Accepted AI attributes, sorted deterministically)
        raw_attributes = ai_data.get("attributes")
        if raw_attributes and isinstance(raw_attributes, dict):
            formatted_attrs: list[str] = []
            for attr_key in sorted(raw_attributes.keys()):
                attr_val = raw_attributes[attr_key]
                # Exclude operational keys if any
                clean_key = normalize_whitespace(str(attr_key))
                formatted_val = cls.format_attribute_value(attr_val)
                if formatted_val:
                    formatted_attrs.append(f"{clean_key}: {formatted_val}")
            if formatted_attrs:
                sections.append(f"Attributes: {'; '.join(formatted_attrs)}")

        # 6. Tags (Accepted AI tags, sorted & deduplicated)
        raw_tags = ai_data.get("tags")
        if raw_tags and isinstance(raw_tags, (list, set, tuple)):
            clean_tags = sorted(
                {normalize_whitespace(str(t)).lower() for t in raw_tags if normalize_whitespace(str(t))}
            )
            if clean_tags:
                sections.append(f"Tags: {', '.join(clean_tags)}")

        # 7. Keywords (Accepted AI keywords, sorted & deduplicated)
        raw_keywords = ai_data.get("keywords")
        if raw_keywords and isinstance(raw_keywords, (list, set, tuple)):
            clean_keywords = sorted(
                {normalize_whitespace(str(k)).lower() for k in raw_keywords if normalize_whitespace(str(k))}
            )
            if clean_keywords:
                sections.append(f"Keywords: {', '.join(clean_keywords)}")

        return "\n".join(sections)
