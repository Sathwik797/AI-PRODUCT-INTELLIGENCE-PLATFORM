# Phase 05 – AI Product Metadata Generation (Step 1: Database & Domain Foundation)

---

# Phase Overview

Phase 05 introduces AI-powered product understanding to the AI Product Intelligence Platform. 

In this initial step (**Step 1: Database & Domain Foundation**), the core relational data model is established to support multimodal AI metadata generation while maintaining strict boundaries between canonical catalog data and AI-generated drafts.

AI metadata generation is explicitly designed to operate at the **Product level**, analyzing all uploaded product images as an ensemble rather than treating images as independent items. Furthermore, AI-generated content is treated as **advisory drafts**—seller approval is required before any AI-generated attribute is accepted or copied into the canonical `products` table.

---

# Conceptual Data Layers

The domain architecture separates product intelligence into three distinct layers:

```text
1. products (Canonical Layer)
   └── Contains seller-approved, verified product data (title, brand, price, sku).

2. product_metadata (Current Active Draft Layer)
   └── Singleton pointer per product identifying the current active AI draft.

3. ai_generations (Historical Generation Log Layer)
   └── Complete historical ledger of every AI generation attempt, execution metrics,
       structured outputs, and granular seller acceptance states.
```

---

# Database Design

## 1. Table: `ai_generations`

Stores the execution history and payload for every AI generation event associated with a product.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | Integer | No | Primary Key, Indexed |
| `product_id` | Integer | No | Foreign Key to `products.id`, Indexed |
| `generation_number` | Integer | No | Sequential run number per product (1, 2, ...) |
| `status` | String(50) | No | Lifecycle state: `pending`, `processing`, `completed`, `failed` |
| `output` | JSON | Yes | Full structured AI output (title, description, attributes, tags) |
| `acceptance_state` | JSON | Yes | Field-level seller review state (`pending`, `accepted`, `modified`, `rejected`) |
| `model_name` | String(100) | Yes | Name of the AI model (e.g. `gemini-1.5-flash`) |
| `model_version` | String(50) | Yes | Specific model checkpoint or version tag |
| `prompt_version` | String(50) | Yes | Version identifier for the prompt template used |
| `schema_version` | String(50) | Yes | Version of the JSON schema expected in output |
| `processing_time` | Float | Yes | AI inference and processing latency in seconds |
| `error_message` | Text | Yes | Diagnostic error message if generation failed |
| `started_at` | DateTime | Yes | Timestamp when inference commenced |
| `completed_at` | DateTime | Yes | Timestamp when generation completed or failed |
| `created_at` | DateTime | No | Record creation timestamp (`server_default=func.now()`) |
| `updated_at` | DateTime | No | Record update timestamp (`onupdate=func.now()`) |

---

## 2. Table: `product_metadata`

Serves as the aggregate pointer to the currently active AI generation draft for a given product. It avoids data duplication by referencing `ai_generations.id`.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | Integer | No | Primary Key, Indexed |
| `product_id` | Integer | No | Foreign Key to `products.id`, **UNIQUE**, Indexed |
| `current_generation_id` | Integer | Yes | Foreign Key to `ai_generations.id` |
| `created_at` | DateTime | No | Creation timestamp (`server_default=func.now()`) |
| `updated_at` | DateTime | No | Update timestamp (`onupdate=func.now()`) |

---

# Entity Relationships

```text
Product (products)
   │
   ├── 1 : N (cascade="all, delete-orphan")
   │   └── Image (images)
   │
   ├── 1 : 1 (uselist=False, cascade="all, delete-orphan")
   │   └── ProductMetadata (product_metadata)
   │          │
   │          └── N : 1 (no cascade)
   │              └── AIGeneration (ai_generations) [current_generation]
   │
   └── 1 : N (cascade="all, delete-orphan")
       └── AIGeneration (ai_generations)
```

### Relationship Design Principles

1. **Non-destructive History:** `ai_generations` records represent immutable historical generation logs. When a seller rejects a generation or selects a new draft in `product_metadata`, the prior `ai_generations` record remains intact. No cascade deletion exists from `product_metadata` to `ai_generations`.
2. **Product Lifecycle Cascade:** If a parent `Product` is permanently deleted, its associated `metadata_record` and historical `ai_generations` are cascade-deleted to maintain database referential integrity.
3. **Product Attribute Cleanliness:** Canonical fields in `products` (`title`, `description`, `brand`, `sku`, `price`) remain completely unaltered in this phase.

---

# Deliverables Completed in Step 1

- Created `AIGeneration` SQLAlchemy model in [app/models/ai_generation.py](file:///c:/Users/HP%20440%20G8/Documents/ai-product-intelligence-platform/app/models/ai_generation.py).
- Created `ProductMetadata` SQLAlchemy model in [app/models/product_metadata.py](file:///c:/Users/HP%20440%20G8/Documents/ai-product-intelligence-platform/app/models/product_metadata.py).
- Extended `Product` model in [app/models/product.py](file:///c:/Users/HP%20440%20G8/Documents/ai-product-intelligence-platform/app/models/product.py) with `metadata_record` (1-to-1) and `ai_generations` (1-to-many) relationships.
- Registered new models in [app/models/\_\_init\_\_.py](file:///c:/Users/HP%20440%20G8/Documents/ai-product-intelligence-platform/app/models/__init__.py).
- Verified automatic DDL generation on MySQL via `Base.metadata.create_all(bind=engine)`.
- Verified existing Product, Category, and Image workflows remain 100% operational.

---

# Next Planned Steps for Phase 05

- **Step 2:** Pydantic schemas for AI generation output, prompt/schema versions, and acceptance feedback.
- **Step 3:** Gemini Vision integration service and prompt orchestration.
- **Step 4:** Repositories and service logic for triggering generations, recording metrics, and applying seller approval.
- **Step 5:** REST API endpoints and background task integration.
