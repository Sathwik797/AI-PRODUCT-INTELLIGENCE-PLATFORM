"""FastAPI Router for Phase 07.2 Grounded RAG Endpoint.

Implements POST /api/v1/rag/query.
Accepts natural language user query and returns grounded conversational answer
with verified structured claims and execution telemetry.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.schemas.rag import RAGQueryRequest, RAGResponse
from app.services.rag_service import RAGService

router = APIRouter(
    prefix="/api/v1/rag",
    tags=["RAG"]
)


def get_rag_service() -> RAGService:
    """Dependency provider for RAGService."""
    return RAGService()


@router.post("/query", response_model=RAGResponse)
def query_rag(
    request: RAGQueryRequest,
    db: Session = Depends(get_db),
    rag_service: RAGService = Depends(get_rag_service)
) -> RAGResponse:
    """Answers a product question with deterministic grounded citation guarantees."""
    return rag_service.answer_query(
        db=db,
        query=request.query
    )
