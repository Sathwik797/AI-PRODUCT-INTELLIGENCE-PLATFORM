"""Query Understanding & QueryParser component.

Implements Q54, Q55, Q56:
- Pluggable QueryParserPort
- DeterministicQueryParser using FilterRegistry
- Token stripping to produce clean residual semantic query
- Extension point for optional future LLM fallback (strict safety boundary: cannot override hard constraints)
"""

from abc import ABC, abstractmethod
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.schemas.search import SearchFilters, SearchQuery
from app.search.filters import FilterRegistry

logger = logging.getLogger(__name__)


class QueryParserPort(ABC):
    """Abstract port for query understanding strategies."""

    @abstractmethod
    def parse(self, raw_query: str, db: Optional[Session] = None) -> SearchQuery:
        """Parses a user search query into structured constraints and semantic query."""
        pass


class DeterministicQueryParser(QueryParserPort):
    """Deterministic, rule-based query parser implementing Q55."""

    def __init__(self, filter_registry: Optional[FilterRegistry] = None):
        self.registry = filter_registry or FilterRegistry()

    def parse(self, raw_query: str, db: Optional[Session] = None) -> SearchQuery:
        """Extracts structured filters and strips recognized tokens to leave a clean residual semantic query."""
        if not raw_query or not raw_query.strip():
            return SearchQuery(
                original_query="",
                semantic_query="",
                filters=SearchFilters()
            )

        filters, semantic_query = self.registry.parse_filters(raw_query, db=db)

        logger.debug(
            f"Parsed query '{raw_query}' -> filters: {filters.model_dump(exclude_none=True)}, "
            f"semantic_query: '{semantic_query}'"
        )

        return SearchQuery(
            original_query=raw_query.strip(),
            semantic_query=semantic_query,
            filters=filters
        )


class LLMQueryParserFallback(QueryParserPort):
    """Extension point for optional LLM fallback query understanding (Q55).

    Strict Safety Boundary:
    Hard e-commerce constraints must NEVER depend solely on an LLM.
    Any deterministic filter already identified takes precedence over LLM interpretation.
    """

    def __init__(self, deterministic_parser: Optional[DeterministicQueryParser] = None):
        self.deterministic_parser = deterministic_parser or DeterministicQueryParser()

    def parse(self, raw_query: str, db: Optional[Session] = None) -> SearchQuery:
        # First execute deterministic extraction
        search_query = self.deterministic_parser.parse(raw_query, db=db)

        # Extension point: if intent is still ambiguous or residual query has complex relational phrases,
        # an LLM adapter can be invoked here to disambiguate semantic intent, but CANNOT relax or override
        # search_query.filters.
        return search_query
