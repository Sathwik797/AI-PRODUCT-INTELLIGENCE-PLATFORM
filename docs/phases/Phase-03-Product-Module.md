# Phase 03 – Product Module

---

# Phase Overview

After successfully implementing the Category Module, the next major milestone was building the Product Module.

The Product Module is the core business component of the AI Product Intelligence Platform. It manages product information while establishing relationships with categories and preparing the system for future AI-powered capabilities such as image understanding, semantic search, embedding generation, and Retrieval-Augmented Generation (RAG).

Unlike the Category Module, this phase introduced significantly more complex concepts, including SQLAlchemy relationships, business validation, partial updates, dynamic attribute assignment, and a deeper understanding of layered architecture.

This phase also strengthened the project's software engineering practices by emphasizing clean separation of responsibilities across models, schemas, repositories, services, and API layers.

---

# Objectives

The objectives of this phase were:

- Design the Product database model.
- Establish relationships between Products and Categories.
- Implement Product CRUD operations.
- Validate product business rules.
- Implement product search functionality.
- Understand SQLAlchemy ORM relationships.
- Deeply understand the Repository Pattern and Service Layer.
- Build production-oriented REST APIs.
- Test the complete module using Swagger UI.

---

# Why Products?

Products represent the primary business entity of the platform.

Future AI capabilities such as image understanding, embedding generation, semantic search, recommendations, and question answering will all revolve around products.

Therefore, implementing a strong Product Module was essential before integrating any AI components.

---

# Product Database Design

The Product table stores information about every product managed by the platform.

## Product Table

| Column | Type | Description |
|---------|------|-------------|
| id | Integer | Primary Key |
| title | String | Product Title |
| description | Text | Product Description |
| brand | String | Product Brand |
| sku | String | Stock Keeping Unit |
| price | Float | Product Price |
| status | String | Product Status |
| category_id | Integer | Foreign Key |
| created_at | DateTime | Creation Timestamp |
| updated_at | DateTime | Last Updated Timestamp |

---

# Product–Category Relationship

Each product belongs to exactly one category.

One category can contain multiple products.

Relationship:

```text
Category

1

↓

∞

Products
```

This relationship was implemented using SQLAlchemy's relationship() function.

---

# SQLAlchemy Relationship

The Product model contains:

```python
category = relationship(
    "Category",
    back_populates="products"
)
```

The Category model contains:

```python
products = relationship(
    "Product",
    back_populates="category"
)
```

This bidirectional relationship allows navigation between related objects without writing explicit SQL JOIN statements.

---

# SQLAlchemy Concepts Learned

This phase introduced several important ORM concepts.

## relationship()

Creates a Python relationship between ORM objects.

It does not create database columns.

---

## back_populates

Synchronizes relationships between two models.

Changes on one side are reflected on the other.

---

## Lazy Loading

Related objects are loaded only when accessed.

---

## Foreign Keys

The `category_id` column establishes the database relationship between Products and Categories.

---

# Product Schemas

Several Pydantic schemas were created.

## ProductBase

Contains common product fields shared by multiple schemas.

---

## ProductCreate

Used when creating products.

Inherits from ProductBase.

---

## ProductUpdate

Supports partial updates.

Every field is optional.

This allows updating only the fields supplied by the client.

---

## ProductResponse

Used for API responses.

Includes:

- id
- timestamps
- model configuration for ORM serialization

---

# Important Pydantic Concepts

Several important concepts were learned.

## model_dump()

Converts Pydantic models into dictionaries.

Used before creating SQLAlchemy objects.

---

## exclude_unset=True

Ensures only supplied fields are updated.

Without this option, unspecified fields could accidentally become `None`.

---

## from_attributes=True

Allows SQLAlchemy ORM objects to be automatically converted into API responses.

---

# Product Repository

The Product Repository was responsible for all database interactions.

Repository methods implemented:

- create()
- update()
- delete()
- get_by_id()
- get_all()
- get_by_sku()
- get_by_category()
- search()

Each method performs exactly one database responsibility.

---

# Product Search

Search functionality was implemented using SQLAlchemy.

The search checks:

- Product Title
- Product Description
- Product Brand

This allows users to retrieve products using keyword-based searches.

This functionality serves as the foundation for future semantic search using embeddings.

---

# Product Service

The Product Service contains all business rules.

Responsibilities include:

- Validate duplicate SKU
- Validate Category existence
- Handle updates
- Handle deletes
- Coordinate repositories
- Enforce business logic

Unlike repositories, services never communicate directly with the database.

---

# Business Rules

Several important validations were introduced.

## Duplicate SKU Validation

Every product must have a unique SKU.

Duplicate SKUs are rejected.

---

## Category Validation

Products cannot be created under categories that do not exist.

---

## Product Validation

Products must exist before being updated or deleted.

---

# Dynamic Updates

Instead of manually assigning every field,

```python
product.title = ...
product.price = ...
```

dynamic updates were implemented using:

```python
setattr(product, field, value)
```

This approach makes update logic cleaner and scalable.

---

# API Layer

REST APIs were created using FastAPI.

Implemented endpoints:

## Create Product

```
POST /products
```

---

## Get All Products

```
GET /products
```

---

## Get Product By ID

```
GET /products/{product_id}
```

---

## Update Product

```
PUT /products/{product_id}
```

---

## Delete Product

```
DELETE /products/{product_id}
```

---

## Get Products By Category

```
GET /products/category/{category_id}
```

---

## Search Products

```
GET /products/search/{keyword}
```

---

# Request Flow

Every Product request follows the layered architecture.

```text
Client

↓

FastAPI Router

↓

Product Service

↓

Product Repository

↓

SQLAlchemy ORM

↓

MySQL Database

↓

Repository

↓

Service

↓

API

↓

Client
```

---

# SQLAlchemy Internals Learned

This phase included an in-depth understanding of SQLAlchemy internals.

Topics explored include:

- Session
- Identity Map
- Unit of Work
- flush()
- commit()
- rollback()
- refresh()
- Relationship Loading

Understanding these concepts helped explain how SQLAlchemy manages object states and database transactions.

---

# Architectural Decisions

Several important design decisions were made.

## Repository Layer

Responsible only for database operations.

No business logic.

---

## Service Layer

Responsible only for business rules.

No SQL queries.

---

## API Layer

Responsible only for HTTP communication.

No business logic.

---

## ORM Models

Represent database entities.

---

## Pydantic Schemas

Represent data transfer objects between the client and the backend.

---

# Software Engineering Principles Applied

Throughout this phase, the following principles were consistently applied.

- Separation of Concerns
- Single Responsibility Principle
- Layered Architecture
- Repository Pattern
- Service Pattern
- Dependency Injection
- Clean Code Practices
- Code Reusability

---

# Testing

The complete Product Module was tested using Swagger UI.

Successfully verified:

- Create Product
- Retrieve Product
- Retrieve All Products
- Update Product
- Delete Product
- Product Search
- Products by Category

Every endpoint returned the expected response without runtime errors.

---

# Challenges Faced

This phase involved significantly more architectural learning than coding.

Major topics explored included:

- SQLAlchemy Relationships
- Repository vs Service responsibilities
- Why Pydantic models cannot be directly added to the database
- Why Services should not raise HTTP exceptions
- Why ProductUpdate should not inherit ProductBase
- Why exclude_unset=True is required
- Dynamic updates using setattr()
- ORM serialization using from_attributes=True

Understanding these concepts greatly improved backend design knowledge.

---

# Deliverables Completed

- Product SQLAlchemy Model
- Product Schemas
- Product Repository
- Product Service
- Product REST APIs
- Product Search
- Product–Category Relationship
- Swagger Testing
- Business Validation
- Complete Layered Implementation

---

# Key Learning Outcomes

By the end of this phase, the following concepts were understood.

- SQLAlchemy Relationships
- Foreign Keys
- Lazy Loading
- Repository Pattern
- Service Layer
- Business Validation
- Dependency Injection
- Pydantic Serialization
- Partial Updates
- Dynamic Attribute Assignment
- REST API Development
- Clean Architecture
- Backend Software Engineering

---

# Phase Summary

The Product Module transformed the project from a simple CRUD backend into a structured, production-oriented application.

More importantly, this phase established the architectural patterns that will support future AI capabilities.

Products now serve as the central entity of the platform, providing the foundation for image management, AI-powered product understanding, embedding generation, semantic search, and Retrieval-Augmented Generation.

With the successful completion of this phase, the backend is now ready to begin integrating artificial intelligence into the application.

---

# Next Phase

**Phase 04 – Image Management**

Objectives:

- Design Image database model
- Establish Product–Image relationship
- Upload product images
- Store image metadata
- Validate uploaded files
- Prepare images for Gemini Vision processing
- Build the foundation for AI-powered product understanding