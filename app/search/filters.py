"""Extensible FilterHandler Architecture & Registry for Phase 07 Hybrid Search.

Implements Q61, Q63, Q64:
- FilterHandler specification interface
- Core 6 handlers: Brand, Category, MinPrice, MaxPrice, Color, Size
- Extraction / normalization of values
- Stripping of matched tokens for residual semantic query
- SQLAlchemy pre-filter construction
- Final eligibility evaluation against authoritative product & metadata
"""

from abc import ABC, abstractmethod
import re
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.models.category import Category
from app.models.product import Product
from app.schemas.search import SearchFilters

# Common color vocabulary for e-commerce
COMMON_COLORS = [
    "black", "white", "red", "blue", "green", "yellow",
    "grey", "gray", "brown", "pink", "purple", "orange",
    "beige", "navy", "gold", "silver", "maroon", "teal", "tan"
]


def clean_spaces(text: str) -> str:
    """Collapses consecutive spaces and strips leading/trailing whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def parse_numeric_value(val_str: str) -> float:
    """Parses numeric string supporting 'k' multiplier (e.g. '5k' -> 5000.0)."""
    cleaned = val_str.lower().strip()
    if cleaned.endswith("k"):
        return float(cleaned[:-1].strip()) * 1000.0
    return float(cleaned)


class FilterHandler(ABC):
    """Abstract interface for a modular search filter handler."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the filter field (matches SearchFilters attribute)."""
        pass

    @abstractmethod
    def extract(self, text: str, db: Optional[Session] = None) -> tuple[Optional[Any], str]:
        """Extracts the filter value from text and returns (extracted_value, residual_text)."""
        pass

    @abstractmethod
    def apply_prefilter(self, query: Query, value: Any) -> Query:
        """Applies this filter as a pre-filter predicate to the SQLAlchemy query."""
        pass

    @abstractmethod
    def matches_product(self, product: Product, value: Any, accepted_metadata: dict[str, Any]) -> bool:
        """Evaluates whether the product satisfies this filter during final eligibility."""
        pass


class PriceFilterHandler(FilterHandler):
    """Handles both min_price and max_price extraction, filtering, and eligibility."""

    @property
    def name(self) -> str:
        return "price"

    def extract(self, text: str, db: Optional[Session] = None) -> tuple[dict[str, Optional[float]], str]:
        """Extracts min_price and max_price from raw query text.

        Patterns supported:
        - "under ₹5000", "below 5k", "less than 5000", "<= 5000", "< 5000"
        - "above ₹1000", "over 1k", "more than 1000", ">= 1000", "> 1000"
        - "between ₹1000 and ₹5000", "1000 to 5000", "1000 - 5000"
        """
        curr_pattern = r"(?:₹|rs\.?|inr|\$|usd|eur|€)?"
        residual = text
        min_p: Optional[float] = None
        max_p: Optional[float] = None

        # 1. Between / Range pattern
        between_match = re.search(
            rf"\bbetween\s+{curr_pattern}\s*(\d+(?:\.\d+)?k?)\s*(?:and|-|to)\s*{curr_pattern}\s*(\d+(?:\.\d+)?k?)\b",
            residual,
            re.IGNORECASE
        )
        if between_match:
            min_p = parse_numeric_value(between_match.group(1))
            max_p = parse_numeric_value(between_match.group(2))
            residual = residual[:between_match.start()] + " " + residual[between_match.end():]

        # 2. Max price pattern: under / below / less than / <= / <
        if max_p is None:
            max_match = re.search(
                rf"\b(?:under|below|less\s+than|<=|<)\s+{curr_pattern}\s*(\d+(?:\.\d+)?k?)\b",
                residual,
                re.IGNORECASE
            )
            if max_match:
                max_p = parse_numeric_value(max_match.group(1))
                residual = residual[:max_match.start()] + " " + residual[max_match.end():]

        # 3. Min price pattern: above / over / more than / >= / >
        if min_p is None:
            min_match = re.search(
                rf"\b(?:above|over|more\s+than|>=|>)\s+{curr_pattern}\s*(\d+(?:\.\d+)?k?)\b",
                residual,
                re.IGNORECASE
            )
            if min_match:
                min_p = parse_numeric_value(min_match.group(1))
                residual = residual[:min_match.start()] + " " + residual[min_match.end():]

        return {"min_price": min_p, "max_price": max_p}, clean_spaces(residual)

    def apply_prefilter(self, query: Query, value: Any) -> Query:
        if not isinstance(value, dict):
            return query
        min_p = value.get("min_price")
        max_p = value.get("max_price")
        if min_p is not None:
            query = query.filter(Product.price >= min_p)
        if max_p is not None:
            query = query.filter(Product.price <= max_p)
        return query

    def matches_product(self, product: Product, value: Any, accepted_metadata: dict[str, Any]) -> bool:
        if not isinstance(value, dict):
            return True
        min_p = value.get("min_price")
        max_p = value.get("max_price")
        if min_p is not None and product.price < min_p:
            return False
        if max_p is not None and product.price > max_p:
            return False
        return True


class BrandFilterHandler(FilterHandler):
    """Handles exact/normalized brand extraction and filtering."""

    @property
    def name(self) -> str:
        return "brand"

    def extract(self, text: str, db: Optional[Session] = None) -> tuple[Optional[str], str]:
        # Retrieve known brands from database if session is available
        known_brands = set()
        if db:
            try:
                results = db.query(Product.brand).filter(Product.brand.isnot(None)).distinct().all()
                for row in results:
                    if row[0]:
                        known_brands.add(row[0].strip())
            except Exception:
                pass

        # Fallback common brands if DB is empty / detached
        if not known_brands:
            known_brands = {
                "Nike", "Adidas", "Puma", "Reebok", "Under Armour",
                "Apple", "Samsung", "Sony", "Dell", "HP", "Lenovo",
                "ErgoDesk", "Logitech", "Levi's", "Zara", "H&M"
            }

        # Sort brands by length descending so multi-word brands match first (e.g. 'Under Armour' before 'Armour')
        sorted_brands = sorted(known_brands, key=len, reverse=True)
        residual = text

        for b in sorted_brands:
            pattern = rf"\b{re.escape(b)}\b"
            match = re.search(pattern, residual, re.IGNORECASE)
            if match:
                extracted_brand = b
                residual = residual[:match.start()] + " " + residual[match.end():]
                return extracted_brand, clean_spaces(residual)

        return None, clean_spaces(residual)

    def apply_prefilter(self, query: Query, value: Any) -> Query:
        if value:
            return query.filter(func.lower(Product.brand) == str(value).lower())
        return query

    def matches_product(self, product: Product, value: Any, accepted_metadata: dict[str, Any]) -> bool:
        if not value:
            return True
        if not product.brand:
            return False
        return product.brand.strip().lower() == str(value).strip().lower()


class CategoryFilterHandler(FilterHandler):
    """Handles taxonomy category extraction, resolution, and filtering."""

    @property
    def name(self) -> str:
        return "category"

    def extract(self, text: str, db: Optional[Session] = None) -> tuple[dict[str, Any], str]:
        """Matches query against known taxonomy categories in DB or common categories."""
        known_categories: list[tuple[int, str]] = []
        if db:
            try:
                cats = db.query(Category.id, Category.name).all()
                known_categories = [(c.id, c.name.strip()) for c in cats]
            except Exception:
                pass

        if not known_categories:
            known_categories = [
                (1, "Electronics"), (2, "Shoes"), (3, "Clothing"),
                (4, "Furniture"), (5, "Accessories")
            ]

        # Sort by length descending
        sorted_cats = sorted(known_categories, key=lambda x: len(x[1]), reverse=True)
        residual = text

        for cat_id, cat_name in sorted_cats:
            # Match singular or plural (e.g. shoe / shoes)
            base_term = re.escape(cat_name.rstrip("s"))
            pattern = rf"\b{base_term}(?:s|es)?\b"
            match = re.search(pattern, residual, re.IGNORECASE)
            if match:
                residual = residual[:match.start()] + " " + residual[match.end():]
                return {
                    "category": cat_name,
                    "category_id": cat_id
                }, clean_spaces(residual)

        return {"category": None, "category_id": None}, clean_spaces(residual)

    def apply_prefilter(self, query: Query, value: Any) -> Query:
        if isinstance(value, dict) and value.get("category_id"):
            return query.filter(Product.category_id == value["category_id"])
        return query

    def matches_product(self, product: Product, value: Any, accepted_metadata: dict[str, Any]) -> bool:
        if not isinstance(value, dict) or not value.get("category_id"):
            return True
        return product.category_id == value["category_id"]


def extract_attribute_value_str(attr_node: Any) -> Optional[str]:
    """Extracts string representation from an AI attribute node (handles nested dicts)."""
    if attr_node is None:
        return None
    if isinstance(attr_node, dict):
        val = attr_node.get("value")
        if isinstance(val, dict):
            val = val.get("value", str(val))
        return str(val) if val is not None else None
    return str(attr_node)


class ColorFilterHandler(FilterHandler):
    """Handles color attribute extraction and eligibility evaluation (Q64)."""

    @property
    def name(self) -> str:
        return "color"

    def extract(self, text: str, db: Optional[Session] = None) -> tuple[Optional[str], str]:
        residual = text
        for color in sorted(COMMON_COLORS, key=len, reverse=True):
            pattern = rf"\b{color}\b"
            match = re.search(pattern, residual, re.IGNORECASE)
            if match:
                residual = residual[:match.start()] + " " + residual[match.end():]
                return color.capitalize(), clean_spaces(residual)
        return None, clean_spaces(residual)

    def apply_prefilter(self, query: Query, value: Any) -> Query:
        # Pre-filter optimization: checks title or description contains color if value provided
        if value:
            color_term = f"%{str(value).lower()}%"
            return query.filter(
                func.lower(Product.title).like(color_term) |
                func.lower(Product.description).like(color_term)
            )
        return query

    def matches_product(self, product: Product, value: Any, accepted_metadata: dict[str, Any]) -> bool:
        if not value:
            return True
        target_color = str(value).lower()

        # 1. Check accepted AI metadata attributes
        attrs = accepted_metadata.get("attributes", {})
        meta_color_val = extract_attribute_value_str(attrs.get("color"))
        if meta_color_val is not None:
            pattern = rf"\b{re.escape(target_color)}\b"
            return bool(re.search(pattern, meta_color_val, re.IGNORECASE))

        # 2. Check canonical title and description text if metadata does not contain color
        text_corpus = f"{product.title or ''} {product.description or ''}"
        pattern = rf"\b{re.escape(target_color)}\b"
        return bool(re.search(pattern, text_corpus, re.IGNORECASE))


class SizeFilterHandler(FilterHandler):
    """Handles size attribute extraction and eligibility evaluation (Q64)."""

    @property
    def name(self) -> str:
        return "size"

    def extract(self, text: str, db: Optional[Session] = None) -> tuple[Optional[str], str]:
        residual = text
        # Pattern 1: "size 9", "size 10.5", "size XL", "size M"
        match = re.search(
            r"\bsize\s*([0-9]+(?:\.[0-9]+)?|[xs|s|m|l|xl|xxl]+)\b",
            residual,
            re.IGNORECASE
        )
        if match:
            extracted_size = match.group(1).upper()
            residual = residual[:match.start()] + " " + residual[match.end():]
            return extracted_size, clean_spaces(residual)

        # Pattern 2: "XL size", "10 size"
        match2 = re.search(
            r"\b([0-9]+(?:\.[0-9]+)?|[xs|s|m|l|xl|xxl]+)\s*size\b",
            residual,
            re.IGNORECASE
        )
        if match2:
            extracted_size = match2.group(1).upper()
            residual = residual[:match2.start()] + " " + residual[match2.end():]
            return extracted_size, clean_spaces(residual)

        return None, clean_spaces(residual)

    def apply_prefilter(self, query: Query, value: Any) -> Query:
        if value:
            size_term = f"%{str(value).lower()}%"
            return query.filter(
                func.lower(Product.title).like(size_term) |
                func.lower(Product.description).like(size_term)
            )
        return query

    def matches_product(self, product: Product, value: Any, accepted_metadata: dict[str, Any]) -> bool:
        if not value:
            return True
        target_size = str(value).lower()

        # 1. Check accepted AI metadata attributes
        attrs = accepted_metadata.get("attributes", {})
        meta_size_val = extract_attribute_value_str(attrs.get("size"))
        if meta_size_val is not None:
            pattern = rf"\b{re.escape(target_size)}\b"
            return bool(re.search(pattern, meta_size_val, re.IGNORECASE))

        # 2. Check title / description text if metadata does not contain size
        text_corpus = f"{product.title or ''} {product.description or ''}"
        pattern = rf"\b{re.escape(target_size)}\b"
        return bool(re.search(pattern, text_corpus, re.IGNORECASE))


class FilterRegistry:
    """Registry coordinating filter extraction and query decomposition (Q63)."""

    def __init__(self, handlers: Optional[list[FilterHandler]] = None):
        self.handlers = handlers or [
            PriceFilterHandler(),
            BrandFilterHandler(),
            CategoryFilterHandler(),
            ColorFilterHandler(),
            SizeFilterHandler(),
        ]

    def parse_filters(self, raw_query: str, db: Optional[Session] = None) -> tuple[SearchFilters, str]:
        """Runs all registered handlers sequentially, extracting filters and purifying the residual text."""
        residual = raw_query
        extracted_filters = SearchFilters()

        for handler in self.handlers:
            if isinstance(handler, PriceFilterHandler):
                prices, residual = handler.extract(residual, db=db)
                extracted_filters.min_price = prices["min_price"]
                extracted_filters.max_price = prices["max_price"]
            elif isinstance(handler, BrandFilterHandler):
                brand_val, residual = handler.extract(residual, db=db)
                extracted_filters.brand = brand_val
            elif isinstance(handler, CategoryFilterHandler):
                cat_info, residual = handler.extract(residual, db=db)
                extracted_filters.category = cat_info.get("category")
                extracted_filters.category_id = cat_info.get("category_id")
            elif isinstance(handler, ColorFilterHandler):
                color_val, residual = handler.extract(residual, db=db)
                extracted_filters.color = color_val
            elif isinstance(handler, SizeFilterHandler):
                size_val, residual = handler.extract(residual, db=db)
                extracted_filters.size = size_val

        # Clean leftover prepositions if any at ends
        cleaned_residual = re.sub(r"\b(for|with|in|of|and|under|below|above)\b", " ", residual, flags=re.IGNORECASE)
        cleaned_residual = clean_spaces(cleaned_residual)
        # If residual is empty (query was purely filters), fall back to original query text
        if not cleaned_residual:
            cleaned_residual = clean_spaces(raw_query)

        return extracted_filters, cleaned_residual

    def get_handler(self, name: str) -> Optional[FilterHandler]:
        for h in self.handlers:
            if h.name == name:
                return h
        return None
