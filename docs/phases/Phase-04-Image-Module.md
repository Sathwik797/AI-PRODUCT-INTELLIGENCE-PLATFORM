# Phase 04 – Image Management Module

## Objective

Extend the AI Product Intelligence Platform by introducing a complete image management system that supports product image uploads, metadata extraction, and persistent storage while maintaining clean architecture principles.

---

# Overview

Until this phase, the platform managed only structured product information stored inside the database.

This phase introduces binary file handling, allowing products to own multiple images while automatically extracting metadata from uploaded files.

The implementation follows the same layered architecture established in previous phases while introducing a dedicated utility service for filesystem operations.

---

# Architecture

```
Client
    │
    ▼
FastAPI Router
    │
    ▼
Image Service
   ├──────────────┐
   ▼              ▼
Repository    FileStorageService
   │              │
   ▼              ▼
MySQL       Local File System
```

The Image Service orchestrates the complete workflow while delegating persistence and filesystem responsibilities to dedicated components.

---

# Features Implemented

## Image Upload

Implemented a multipart/form-data upload endpoint.

```
POST /products/{product_id}/images
```

The endpoint accepts an uploaded image and associates it with an existing product.

---

## Product Validation

Before saving an image, the service verifies that the target product exists.

Images cannot exist independently without a parent product.

---

## Automatic Folder Creation

Images are organized using the following directory structure:

```
uploads/
└── products/
    └── {product_id}/
```

Each product owns its own folder, making storage organized and easy to manage.

---

## Unique Filename Generation

Original filenames are never used directly.

Instead, UUID-based filenames are generated while preserving the original file extension.

Example:

```
b18944a9-a54a-47f4-af55-ed2f6fbe01e5.jpg
```

Benefits:

- Prevents filename collisions
- Improves security
- Prevents browser cache conflicts
- Makes URLs difficult to guess

---

## Metadata Extraction

Image metadata is calculated by the backend.

The client never provides:

- Width
- Height
- File Size
- MIME Type

These values are extracted automatically using Pillow and Python's filesystem APIs.

Stored metadata includes:

- Width
- Height
- MIME Type
- File Size

---

## Display Order

Each uploaded image receives an automatically assigned display order.

First image:

```
display_order = 1
```

Second image:

```
display_order = 2
```

and so on.

---

## Rollback Strategy

Image upload is treated as a coordinated operation involving both the filesystem and the database.

Workflow:

```
Save File
    │
    ▼
Create Database Record
```

If database persistence fails after the file has already been saved:

```
Delete Uploaded File
```

This guarantees that orphaned files are never left behind.

---

# FileStorageService

Introduced a dedicated utility service responsible for filesystem operations.

Responsibilities include:

- Creating product folders
- Generating UUID filenames
- Saving uploaded files
- Deleting files
- Extracting image metadata

This keeps filesystem logic completely separate from business logic.

---

# Image Repository

Implemented repository methods for:

- create()
- get_by_id()
- get_by_product()
- update()
- delete()

The repository remains responsible only for database persistence.

---

# Image Service

The service coordinates the complete upload workflow.

Responsibilities include:

- Product validation
- File storage
- Metadata extraction
- Display order assignment
- ORM object creation
- Database persistence
- Rollback handling

Business logic remains isolated from persistence.

---

# Image API

Implemented:

```
POST /products/{product_id}/images
```

The endpoint accepts:

- product_id
- UploadFile

Unlike previous modules, this endpoint consumes multipart/form-data instead of JSON.

---

# Technologies Introduced

New libraries:

- Pillow
- python-multipart

New Python modules:

- pathlib
- shutil
- mimetypes
- uuid

---

# Architectural Concepts Learned

During this phase the following software engineering concepts were explored:

- Binary File Uploads
- multipart/form-data
- UploadFile
- Filesystem Management
- UUID Filename Generation
- Metadata Extraction
- Rollback Strategy
- Service Orchestration
- Utility Services
- Layered Architecture
- Separation of Concerns
- Transaction Thinking
- Repository Pattern
- Business Logic Isolation

---

# Current Project Status

Completed Modules:

- Phase 01 – Project Setup
- Phase 02 – Category Module
- Phase 03 – Product Module
- Phase 04 – Image Module

The platform now supports both structured product information and binary image assets.

This image management foundation will be used in later phases for AI-powered image understanding, caption generation, embeddings, and retrieval.