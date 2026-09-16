"""FastAPI Router for Phase 07 Hybrid Search Endpoint.

Implements Q62:
- GET /api/v1/search?q=...&limit=20&debug=false
- Returns strongly typed SearchResponse with results and telemetry metadata
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.schemas.search import SearchResponse
from app.services.hybrid_search_service import HybridSearchService

router = APIRouter(
    prefix="/api/v1/search",
    tags=["Search"]
)


def get_search_service() -> HybridSearchService:
    """Dependency provider for HybridSearchService."""
    return HybridSearchService()


@router.get("", response_model=SearchResponse)
def search_products(
    q: str = Query(..., min_length=1, max_length=500, description="E-commerce natural language search query."),
    limit: Optional[int] = Query(20, ge=1, le=100, description="Maximum number of search results to return."),
    debug: bool = Query(False, description="Whether to include internal diagnostic metadata in response."),
    db: Session = Depends(get_db),
    search_service: HybridSearchService = Depends(get_search_service)
) -> SearchResponse:
    """Executes hybrid search combining MySQL structured constraints and FAISS semantic similarity."""
    return search_service.search(
        db=db,
        raw_query=q,
        limit=limit,
        debug=debug
    )
