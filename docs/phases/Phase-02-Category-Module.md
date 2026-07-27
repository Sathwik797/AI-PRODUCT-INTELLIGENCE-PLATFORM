# Phase 02 – Category Module

---

# Phase Overview

After establishing the backend foundation in Phase 01, the next step was to implement the first business module of the application: **Category Management**.

Categories act as the primary classification mechanism for products. Every product in the system belongs to a category, making this module the foundation for future product management, image management, semantic search, and AI-powered recommendations.

The Category Module was also used to establish the complete backend development workflow that would be followed throughout the project. This included designing database models, creating request and response schemas, implementing repositories and services, exposing REST APIs, and testing the entire feature using Swagger UI.

---

# Objectives

The objectives of this phase were:

- Design the Category database model.
- Create SQLAlchemy ORM mappings.
- Implement CRUD operations.
- Introduce the Repository Pattern.
- Introduce the Service Layer.
- Create REST APIs using FastAPI.
- Validate requests using Pydantic.
- Test APIs using Swagger UI.
- Establish a reusable development workflow for future modules.

---

# Why Categories?

Products need to be organized into logical groups.

Examples:

- Electronics
- Clothing
- Shoes
- Furniture
- Accessories

Using categories provides several advantages:

- Easier product organization
- Better searching and filtering
- Better analytics
- Simplified product management
- Future AI categorization support

Categories also establish relationships that will later be used by Products.

---

# Database Design

The Category table stores basic information about product categories.

## Category Table

| Column | Type | Description |
|---------|------|-------------|
| id | Integer | Primary Key |
| name | String | Category Name |
| created_at | DateTime | Creation Timestamp |
| updated_at | DateTime | Last Updated Timestamp |

---

# SQLAlchemy Model

The Category model was implemented using SQLAlchemy ORM.

The model is responsible for:

- Mapping Python objects to database tables.
- Defining table columns.
- Defining constraints.
- Managing relationships with future Product records.

---

# Repository Pattern

The Category module introduced the Repository Pattern.

Repository responsibilities:

- Insert category
- Update category
- Delete category
- Retrieve category
- Retrieve all categories

Repositories communicate directly with SQLAlchemy and contain only database-related logic.

They do not contain business rules.

---

# Repository Methods

The following repository methods were implemented:

- create()
- update()
- delete()
- get_by_id()
- get_all()
- get_by_name()

Each method performs a single database operation.

---

# Why Repository Pattern?

Separating database logic into repositories provides several benefits.

- Improves maintainability.
- Makes code reusable.
- Keeps SQLAlchemy isolated.
- Simplifies testing.
- Allows services to focus only on business logic.

Instead of allowing APIs to directly communicate with SQLAlchemy, all database operations pass through repositories.

---

# Service Layer

The Service Layer was introduced to hold business logic.

Responsibilities include:

- Prevent duplicate category names.
- Validate input.
- Coordinate repository operations.
- Handle application-specific rules.

The service layer acts as the bridge between APIs and repositories.

---

# Service Methods

The following methods were implemented.

- create_category()
- update_category()
- delete_category()
- get_category_by_id()
- get_all_categories()

Each method validates business rules before interacting with the repository.

---

# Why Service Layer?

The service layer separates business logic from API logic.

Without a service layer:

```text
API

↓

SQLAlchemy
```

Business rules would become scattered throughout API files.

Instead, the architecture becomes:

```text
API

↓

Service

↓

Repository

↓

Database
```

This makes the application easier to maintain and extend.

---

# Pydantic Schemas

Pydantic models were introduced for request validation and response serialization.

The following schemas were implemented.

## CategoryCreate

Used for creating a category.

---

## CategoryUpdate

Used for updating category information.

Supports partial updates.

---

## CategoryResponse

Used for API responses.

Converts SQLAlchemy ORM objects into JSON responses.

---

# API Layer

REST APIs were implemented using FastAPI.

The API layer is responsible for:

- Receiving HTTP requests.
- Validating request data.
- Calling the service layer.
- Returning responses.

No business logic is implemented inside the API layer.

---

# API Endpoints

## Create Category

```
POST /categories
```

Creates a new category.

---

## Get All Categories

```
GET /categories
```

Returns all available categories.

---

## Get Category By ID

```
GET /categories/{category_id}
```

Returns a specific category.

---

## Update Category

```
PUT /categories/{category_id}
```

Updates category information.

---

## Delete Category

```
DELETE /categories/{category_id}
```

Deletes an existing category.

---

# Request Flow

Every request follows the same architecture.

```text
Client

↓

FastAPI Router

↓

Category Service

↓

Category Repository

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

# Concepts Learned

This phase introduced several important backend concepts.

## SQLAlchemy ORM

Understanding how Python classes represent database tables.

---

## Repository Pattern

Separating database access from business logic.

---

## Service Layer

Keeping business rules independent from HTTP requests.

---

## Dependency Injection

Injecting database sessions using FastAPI dependencies.

---

## Pydantic Validation

Automatic request validation.

Automatic response serialization.

---

## CRUD Operations

- Create
- Read
- Update
- Delete

---

## REST API Design

Creating standardized API endpoints using HTTP methods.

---

# Design Decisions

Several architectural decisions were made during this phase.

## APIs should not contain business logic.

Business rules belong inside the Service Layer.

---

## Services should not directly communicate with the database.

Services communicate through repositories.

---

## Repositories should not validate business rules.

Repositories only perform database operations.

---

## Models and Schemas should remain separate.

SQLAlchemy models represent database entities.

Pydantic schemas represent data transfer objects.

---

# Testing

All Category APIs were tested using Swagger UI.

The following operations were successfully verified.

- Create Category
- Retrieve Category
- Retrieve All Categories
- Update Category
- Delete Category

All endpoints returned expected responses.

---

# Challenges Faced

During implementation several important architectural questions were explored.

These included:

- Why separate repositories from services?
- Why use Pydantic instead of SQLAlchemy models for requests?
- Why should APIs remain thin?
- How should database sessions be managed?

Understanding these concepts established a strong backend development workflow that would be reused throughout the project.

---

# Deliverables Completed

- Category Database Model
- Category SQLAlchemy Model
- Category Repository
- Category Service
- Category Schemas
- Category REST APIs
- Swagger Testing
- Layered Architecture Implementation

---

# Key Learning Outcomes

By completing this phase, the following concepts were understood.

- SQLAlchemy ORM Basics
- Repository Pattern
- Service Layer
- REST API Development
- CRUD Operations
- Pydantic Validation
- Dependency Injection
- Layered Architecture
- Separation of Concerns
- Backend Project Organization

---

# Phase Summary

The Category Module became the first complete backend feature implemented in the project.

More importantly, it established the development pattern that would be reused for every future module.

Every subsequent feature—including Products, Images, AI Processing, Embeddings, and Semantic Search—would follow the same layered architecture introduced during this phase.

This module transformed the project from a configured backend into a functional application capable of managing business data using production-oriented software engineering practices.

---

# Next Phase

**Phase 03 – Product Module**

Objectives:

- Implement Product Management
- Establish Product–Category Relationships
- Learn SQLAlchemy Relationships
- Implement Product CRUD
- Implement Search
- Apply Business Validation
- Deeply understand ORM relationships and backend architecture