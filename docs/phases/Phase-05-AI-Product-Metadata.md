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

---

# Step 6: Asynchronous AI Generation & REST API Architecture

Step 6 introduces asynchronous generation orchestration and REST endpoints to trigger and query product metadata generation without blocking the HTTP request thread.

## 1. Endpoints

### `POST /products/{product_id}/ai/generate`
- **Purpose**: Initiates asynchronous generation for the given product.
- **Status Code**: `202 Accepted`
- **Response Payload**:
  ```json
  {
    "generation_id": 1,
    "product_id": 10,
    "status": "pending"
  }
  ```
- **Execution Flow**:
  1. Validates that the product exists.
  2. Creates exactly **one** `AIGeneration` record with `status="pending"`.
  3. Commits the record to guarantee persistence.
  4. Dispatches background processing via `BackgroundTasks` with the created `generation_id`.
  5. Returns HTTP 202 immediately to the caller.

### `GET /products/{product_id}/ai/generations/{generation_id}`
- **Purpose**: Queries execution status, latency, error details, and generated metadata.
- **Status Code**: `200 OK` (or `404 Not Found` if the generation does not exist or does not match `product_id`).
- **Response Payload (Completed)**:
  ```json
  {
    "generation_id": 1,
    "product_id": 10,
    "generation_number": 1,
    "status": "completed",
    "output": { ... },
    "acceptance_state": { "title": "pending", "description": "pending", ... },
    "processing_time": 1.452,
    "error_message": null,
    "started_at": "2026-09-07T22:30:00Z",
    "completed_at": "2026-09-07T22:30:01Z",
    "created_at": "2026-09-07T22:29:59Z"
  }
  ```

---

## 2. BackgroundTasks & Session Isolation Architecture

```
HTTP POST Request Lifecycle
   Client Request
        ↓
   [POST /products/{id}/ai/generate]
        ↓
   FastAPI Depends(get_db) creates request Session
        ↓
   AIGenerationService.create_pending_generation(db, product_id)
        ↓
   Persists AIGeneration (status='pending', generation_id=N)
        ↓
   Schedule BackgroundTasks(process_generation_task, generation_id=N)
        ↓
   HTTP 202 Accepted Response returned to client
   (Request DB session closes)

---------------------------------------------------------------------
Background Task Lifecycle (Post-Response)
   process_generation_task(generation_id=N)
        ↓
   Fresh Session: db = SessionLocal()
        ↓
   AIGenerationService.process_generation(db, generation_id=N)
        ↓
   Idempotency Check: if status is completed/failed/processing, skip
        ↓
   Transition: pending → processing
        ↓
   GeminiProvider.generate_product_metadata(...)
        ↓
   Atomic Success Transaction:
      - Update AIGeneration (status='completed', output, acceptance_state)
      - Update ProductMetadata.current_generation_id = N
      - db.commit()
        ↓
   finally:
      db.close() (Guaranteed connection return to pool)
```

---

## 3. Key Design Decisions & Guarantees

1. **Exact Generation Ownership (Zero Duplicate Generations)**:
   - The generation record created by the POST endpoint is the exact record processed by the background task.
   - The background task calls `process_generation(db, generation_id)`, NEVER `generate(db, product_id)`.
2. **Processing Idempotency**:
   - Only records in `pending` state may transition to `processing`.
   - If `process_generation` is invoked on a generation that is already `processing`, `completed`, or `failed`, it returns immediately without re-invoking Gemini.
3. **Database Session Safety**:
   - The background task instantiates its own isolated `SessionLocal()` and closes it in a `finally` block, ensuring no stale or leaked sessions.
4. **No External Task Queue (FastAPI BackgroundTasks)**:
   - Built on FastAPI's lightweight `BackgroundTasks` without external infrastructure (Celery, Redis, RabbitMQ).
   - *Note*: FastAPI BackgroundTasks executes in-process and is not a durable distributed queue. Future scaling can replace the adapter function with a durable queue worker without changing the service or API contract.
5. **Generation Numbering Concurrency Limitation**:
   - Sequential numbering is calculated via `MAX(generation_number) + 1`. In high-concurrency environments with parallel requests, database-level locking or unique constraints would be needed to prevent race conditions.

---

---

# Step 7: AI Metadata Acceptance & Seller Review

Step 7 introduces the **Human-in-the-Loop Seller Review & Acceptance boundary**, enabling sellers to review advisory AI metadata and merge approved fields into canonical product records.

## 1. Architectural Invariants

1. **Zero Direct AI Overwrites**:
   - AI generation outputs are never written directly to the `products` table. Only explicit seller review or acceptance copies approved values.
2. **Canonical Column Boundary**:
   - The canonical `products` table has strict columns: `title`, `description`, `brand`, `sku`, `price`, `status`, `category_id`.
   - AI metadata suggestions for `title`, `description`, `brand`, and `category` map to canonical columns.
   - Non-canonical fields (`tags`, `keywords`, `attributes`) are accepted for indexing and discovery in `ai_generations.acceptance_state`, but never written to `products` or returned in `applied_fields`.
3. **Immutable Historical Output**:
   - `ai_generations.output` remains completely immutable and preserves the exact Gemini output.
   - Review transitions update `ai_generations.acceptance_state` only.
4. **Field-Level State Machine**:
   - Each field tracks: `pending` -> `accepted` | `modified` | `rejected`.
5. **Manual Seller Edit Synchronization**:
   - When a seller later manually edits a canonical field (`PUT /products/{id}`) that was previously `accepted` from the active AI generation, `ProductService.update()` automatically transitions that field's state to `modified`.
6. **Atomic Multi-Entity Transactions**:
   - Updating `Product` columns and `AIGeneration.acceptance_state` executes within the exact same database transaction (`commit=False` followed by atomic `db.commit()`).

---

## 2. Endpoints

### `GET /products/{product_id}/ai/current`
- **Purpose**: Retrieves the active current AI generation, execution metrics, output, and acceptance state.
- **Status Code**: `200 OK`

### `POST /products/{product_id}/ai/accept-all`
- **Purpose**: One-click acceptance of all AI-generated fields for the active generation.
- **Status Code**: `200 OK`
- **Response**: `AIAcceptanceResponse` with `applied_fields` (canonical only) and updated `acceptance_state`.

### `POST /products/{product_id}/ai/review`
- **Purpose**: Granular field-by-field review (`accept`, `modify`, `reject`, `pending`).
- **Status Code**: `200 OK`
- **Request Body**:
  ```json
  {
    "decisions": {
      "title": { "action": "accept" },
      "description": { "action": "modify", "modified_value": "Seller revised copy" },
      "brand": { "action": "reject" },
      "category": { "action": "accept" },
      "tags": { "action": "accept" }
    }
  }
  ```
- **Response**: `AIAcceptanceResponse`

---

## 3. Dedicated Service Architecture

- **`AIAcceptanceService`** (`app/services/ai_acceptance_service.py`):
  - Encapsulates review state transitions, field-specific business validation (lengths, non-empty title, category existence in DB), atomic transaction coordination, and the `on_manual_product_update()` sync hook.
- **`ProductService`** (`app/services/product_service.py`):
  - Injects `AIAcceptanceService` explicitly to synchronize seller updates.


