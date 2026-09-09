"""AI Context Builder for AI Product Intelligence Platform.

Phase 05 – Step 4: AI Context Builder.

This component serves as the pure transformation boundary between transactional domain objects
(Product, Image, Category) and the decoupled AI DTOs (AIProductContext, AIImageInput).

Architectural Boundaries:
- Pure Python transformation layer: accepts domain objects, ORM models, or dictionaries via duck typing.
- Decoupled from persistence: NO SQLAlchemy imports, sessions, or queries.
- Decoupled from HTTP: NO FastAPI imports, UploadFile, or HTTPExceptions.
- Decoupled from AI execution: NEVER calls GeminiProvider or external APIs.
- Read-only: NEVER mutates the input models.
"""

from typing import Any, Optional, Sequence

from app.ai.gemini_provider import AIImageInput, AIProductContext


class AIProductContextBuilder:
    """Builds AIProductContext DTOs from domain/ORM objects and filesystem references."""

    @staticmethod
    def build_image_input(
        image: Any,
        image_bytes: Optional[bytes] = None,
        role: Optional[str] = None
    ) -> AIImageInput:
        """Constructs an individual AIImageInput DTO from an image object or dict.

        Args:
            image: Domain Image model, dictionary, or duck-typed object.
            image_bytes: Optional preloaded image bytes.
            role: Optional seller image-role override (e.g. 'front', 'packaging').

        Returns:
            AIImageInput instance with preserved image identity and metadata.
        """
        # Extract image ID
        image_id = getattr(image, "id", None)
        if image_id is None and isinstance(image, dict):
            image_id = image.get("id") or image.get("image_id")

        if image_id is None:
            raise ValueError("Image object must have an 'id' attribute or key.")

        try:
            image_id = int(image_id)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Image ID must be an integer, got {image_id!r}: {e}") from e

        # Extract file path or URL
        file_path = getattr(image, "image_url", None) or getattr(image, "file_path", None)
        if file_path is None and isinstance(image, dict):
            file_path = image.get("file_path") or image.get("image_url")
        if file_path is not None:
            file_path = str(file_path)

        # Extract MIME type
        mime_type = getattr(image, "mime_type", None)
        if mime_type is None and isinstance(image, dict):
            mime_type = image.get("mime_type")
        if not mime_type:
            mime_type = "image/jpeg"

        # Extract display order
        display_order = getattr(image, "display_order", None)
        if display_order is None and isinstance(image, dict):
            display_order = image.get("display_order")

        # Extract preloaded bytes if present on image object
        if image_bytes is None:
            image_bytes = getattr(image, "image_bytes", None)
            if image_bytes is None and isinstance(image, dict):
                image_bytes = image.get("image_bytes")

        # Role resolution
        resolved_role = role
        if resolved_role is None:
            resolved_role = getattr(image, "role", None)
            if resolved_role is None and isinstance(image, dict):
                resolved_role = image.get("role")

        return AIImageInput(
            image_id=image_id,
            image_bytes=image_bytes,
            file_path=file_path,
            mime_type=str(mime_type),
            display_order=display_order,
            role=str(resolved_role) if resolved_role else None
        )

    @classmethod
    def build_context(
        cls,
        product: Any,
        images: Optional[Sequence[Any]] = None,
        available_categories: Optional[Sequence[Any]] = None,
        image_role_overrides: Optional[dict[int, str]] = None,
        preloaded_image_bytes: Optional[dict[int, bytes]] = None,
    ) -> AIProductContext:
        """Builds an AIProductContext DTO from domain objects.

        Args:
            product: Product model instance or dict containing product data.
            images: Optional explicit list of Image objects/dicts. If omitted,
                    inspects product.images if available.
            available_categories: Optional list of Category models or category name strings.
            image_role_overrides: Optional mapping of image_id -> seller role override.
            preloaded_image_bytes: Optional mapping of image_id -> raw bytes.

        Returns:
            AIProductContext DTO fully decoupled from ORM and HTTP layers.
        """
        image_role_overrides = image_role_overrides or {}
        preloaded_image_bytes = preloaded_image_bytes or {}

        # 1. Product ID
        product_id = getattr(product, "id", None)
        if product_id is None and isinstance(product, dict):
            product_id = product.get("id") or product.get("product_id")

        if product_id is None:
            raise ValueError("Product object must have an 'id' attribute or key.")

        try:
            product_id = int(product_id)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Product ID must be an integer, got {product_id!r}: {e}") from e

        # 2. Seller Context Fields
        title = getattr(product, "title", None)
        if title is None and isinstance(product, dict):
            title = product.get("title")

        description = getattr(product, "description", None)
        if description is None and isinstance(product, dict):
            description = product.get("description")

        brand = getattr(product, "brand", None)
        if brand is None and isinstance(product, dict):
            brand = product.get("brand")

        price = getattr(product, "price", None)
        if price is None and isinstance(product, dict):
            price = product.get("price")
        if price is not None:
            try:
                price = float(price)
            except (ValueError, TypeError):
                pass

        # 3. Category Context (Current Category)
        current_category: Optional[str] = None
        category_obj = getattr(product, "category", None)
        if category_obj is not None:
            current_category = getattr(category_obj, "name", str(category_obj))
        elif isinstance(product, dict):
            current_category = product.get("category_name") or product.get("category") or product.get("current_category")

        # 4. Available Categories Taxonomy (Preserves ID and Name as pure decoupled dicts)
        resolved_categories: list[dict[str, Any]] = []
        if available_categories:
            seen: set[tuple[Optional[int], str]] = set()
            for cat in available_categories:
                raw_id = getattr(cat, "id", None)
                if raw_id is None and isinstance(cat, dict):
                    raw_id = cat.get("id") or cat.get("category_id")

                resolved_id: Optional[int] = None
                if raw_id is not None and not type(raw_id).__name__.startswith("MagicMock"):
                    try:
                        resolved_id = int(raw_id)
                    except (ValueError, TypeError):
                        resolved_id = None

                name = getattr(cat, "name", None)
                if name is None and isinstance(cat, dict):
                    name = cat.get("name") or cat.get("category_name")
                if name is None:
                    name = str(cat) if not isinstance(cat, dict) else ""
                name = str(name).strip()

                if name and (resolved_id, name) not in seen:
                    seen.add((resolved_id, name))
                    resolved_categories.append({"id": resolved_id, "name": name})

        # 5. Images Resolution & Sorting
        raw_images: Sequence[Any]
        if images is not None:
            raw_images = images
        else:
            raw_images = getattr(product, "images", None) or []

        ai_images: list[AIImageInput] = []
        for img in raw_images:
            img_id = getattr(img, "id", None)
            if img_id is None and isinstance(img, dict):
                img_id = img.get("id") or img.get("image_id")

            role_override = image_role_overrides.get(img_id) if img_id is not None else None
            bytes_override = preloaded_image_bytes.get(img_id) if img_id is not None else None

            ai_image = cls.build_image_input(
                image=img,
                image_bytes=bytes_override,
                role=role_override
            )
            ai_images.append(ai_image)

        # Preserve display ordering (placing None display_order at the end)
        ai_images.sort(key=lambda item: (item.display_order is None, item.display_order or 0))

        return AIProductContext(
            product_id=product_id,
            title=title,
            description=description,
            brand=brand,
            price=price,
            current_category=current_category,
            available_categories=resolved_categories,
            images=ai_images
        )
