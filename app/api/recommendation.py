"""FastAPI Router for Phase 08 Product Recommendations.

Implements Q93:
- GET /api/v1/products/{product_id}/recommendations?limit=5
- Returns strongly typed RecommendationResponse with normalized scores, match reasons, and telemetry.
- Raises 404 if source product is not found.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.recommendation.candidate_retriever import RecommendationRetrievalError
from app.schemas.recommendation import RecommendationResponse
from app.services.recommendation_service import (
    ProductNotFoundError,
    RecommendationService,
)

router = APIRouter(
    prefix="/api/v1/products",
    tags=["Recommendations"]
)


def get_recommendation_service() -> RecommendationService:
    """Dependency provider for RecommendationService."""
    return RecommendationService()


@router.get("/{product_id}/recommendations", response_model=RecommendationResponse)
def get_product_recommendations(
    product_id: int,
    limit: Optional[int] = Query(5, ge=1, le=50, description="Number of recommendations to return."),
    db: Session = Depends(get_db),
    service: RecommendationService = Depends(get_recommendation_service)
) -> RecommendationResponse:
    """Generates hybrid recommendations for a target product."""
    try:
        return service.get_recommendations(
            db=db,
            product_id=product_id,
            limit=limit
        )
    except ProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RecommendationRetrievalError as e:
        raise HTTPException(status_code=500, detail=str(e))
