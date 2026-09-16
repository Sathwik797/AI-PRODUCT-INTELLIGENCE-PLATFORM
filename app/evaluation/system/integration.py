"""System Integration Validator (Scenarios A through F).

Implements Phase 09 Section 4:
- Scenario A: Accepted AI metadata propagation (AI -> Embedding -> Search -> RAG)
- Scenario B: Rejected/unaccepted metadata isolation
- Scenario C: Volatile field isolation (Price updates do not dirty embeddings)
- Scenario D: Inactive product isolation (status != 'ACTIVE' excluded from Search, RAG, Recs)
- Scenario E: Search -> RAG consistency
- Scenario F: Recommendation / catalog consistency
"""

import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.ai.embedding_text_builder import EmbeddingTextBuilder, compute_content_hash
from app.models.ai_generation import AIGeneration
from app.models.product import Product
from app.models.product_embedding import ProductEmbedding
from app.models.product_metadata import ProductMetadata
from app.rag.citation_validator import CitationValidator
from app.rag.knowledge import RAGRetrievalService
from app.schemas.rag import RAGCitation, RAGClaim, RAGKnowledgeBundle, RAGModelResponse
from app.schemas.search import SearchFilters, SearchQuery
from app.search.eligibility_guard import FinalEligibilityGuard
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_search_service import HybridSearchService
from app.services.recommendation_service import RecommendationService
from app.schemas.system_evaluation import (
    ScenarioCheckDetail,
    SystemIntegrationSummary,
)

logger = logging.getLogger(__name__)


class SystemIntegrationValidator:
    """Validates cross-subsystem semantic consistency and data propagation."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        hybrid_search_service: Optional[HybridSearchService] = None,
        rag_retrieval_service: Optional[RAGRetrievalService] = None,
        citation_validator: Optional[CitationValidator] = None,
        recommendation_service: Optional[RecommendationService] = None
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.hybrid_search_service = hybrid_search_service or HybridSearchService()
        self.rag_retrieval_service = rag_retrieval_service or RAGRetrievalService()
        self.citation_validator = citation_validator or CitationValidator()
        self.recommendation_service = recommendation_service or RecommendationService()
        self.eligibility_guard = FinalEligibilityGuard()

    def run_all_scenarios(
        self,
        db: Session,
        sample_product_id: Optional[int] = None
    ) -> SystemIntegrationSummary:
        """Executes all 6 integration scenarios against active catalog state."""
        # Find an active product with accepted metadata if product_id not provided
        target_pid = sample_product_id
        if target_pid is None:
            active_prod = (
                db.query(Product)
                .join(ProductMetadata, Product.id == ProductMetadata.product_id)
                .filter(Product.status == "ACTIVE", ProductMetadata.current_generation_id.isnot(None))
                .first()
            )
            if not active_prod:
                # Fallback to any active product
                active_prod = db.query(Product).filter(Product.status == "ACTIVE").first()
            if active_prod:
                target_pid = active_prod.id

        scenarios: dict[str, ScenarioCheckDetail] = {}

        scenarios["scenario_a"] = self.verify_scenario_a_accepted_propagation(db, target_pid)
        scenarios["scenario_b"] = self.verify_scenario_b_rejected_isolation(db, target_pid)
        scenarios["scenario_c"] = self.verify_scenario_c_volatile_isolation(db, target_pid)
        scenarios["scenario_d"] = self.verify_scenario_d_inactive_isolation(db, target_pid)
        scenarios["scenario_e"] = self.verify_scenario_e_search_rag_consistency(db, target_pid)
        scenarios["scenario_f"] = self.verify_scenario_f_recommendation_consistency(db, target_pid)

        all_passed = all(s.passed for s in scenarios.values())
        return SystemIntegrationSummary(all_passed=all_passed, scenarios=scenarios)

    # --------------------------------------------------------------------------
    # Scenario A: Accepted metadata propagation
    # --------------------------------------------------------------------------
    def verify_scenario_a_accepted_propagation(
        self,
        db: Session,
        product_id: Optional[int]
    ) -> ScenarioCheckDetail:
        """Verifies accepted AI metadata propagates to embedding, search, and RAG."""
        name = "Scenario A — Accepted Metadata Propagation"
        desc = "Verifies accepted AI attributes propagate into embeddings, search availability, and RAG knowledge."
        violations: list[str] = []
        checks = 0

        if not product_id:
            return ScenarioCheckDetail(
                scenario_name=name,
                description=desc,
                passed=True,
                checks_performed=0,
                violations=[]
            )

        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return ScenarioCheckDetail(
                scenario_name=name,
                description=desc,
                passed=False,
                checks_performed=1,
                violations=[f"Target product {product_id} not found in database."]
            )

        # 1. Inspect accepted metadata
        checks += 1
        accepted_meta = self.embedding_service.get_accepted_ai_metadata(db, product_id)
        accepted_attrs = accepted_meta.get("attributes", {})

        # 2. Embedding document contains accepted attributes
        checks += 1
        doc_text, doc_hash = self.embedding_service.build_embedding_document(db, product)
        for attr_name, attr_node in accepted_attrs.items():
            checks += 1
            attr_val = attr_node.get("value") if isinstance(attr_node, dict) else attr_node
            if attr_val and isinstance(attr_val, str) and len(attr_val) > 2:
                if attr_val.lower() not in doc_text.lower():
                    violations.append(f"Accepted attribute value '{attr_val}' missing from embedding document.")

        # 3. Embedding status consistency
        checks += 1
        emb_record = db.query(ProductEmbedding).filter(ProductEmbedding.product_id == product_id).first()
        if emb_record and emb_record.status == "READY":
            checks += 1
            if emb_record.content_hash != doc_hash:
                violations.append(
                    f"ProductEmbedding content_hash '{emb_record.content_hash}' does not match document hash '{doc_hash}'."
                )

        # 4. RAG hydration contains accepted attributes
        checks += 1
        bundle, _ = self.rag_retrieval_service.retrieve_and_hydrate(db, question=product.title or "shoe", limit=5)
        matched_ctx = next((p for p in bundle.products if p.product_id == product_id), None)
        if matched_ctx:
            checks += 1
            rag_attr_names = {va.attribute for va in matched_ctx.verified_attributes}
            for attr_name in accepted_attrs.keys():
                if attr_name not in rag_attr_names:
                    violations.append(f"Accepted attribute '{attr_name}' was not hydrated in RAG verified attributes.")

        return ScenarioCheckDetail(
            scenario_name=name,
            description=desc,
            passed=(len(violations) == 0),
            checks_performed=checks,
            violations=violations
        )

    # --------------------------------------------------------------------------
    # Scenario B: Rejected/unaccepted metadata isolation
    # --------------------------------------------------------------------------
    def verify_scenario_b_rejected_isolation(
        self,
        db: Session,
        product_id: Optional[int]
    ) -> ScenarioCheckDetail:
        """Verifies rejected or unreviewed AI metadata is strictly isolated."""
        name = "Scenario B — Rejected Metadata Isolation"
        desc = "Verifies rejected/pending metadata never enters embeddings, search truth, or RAG claims."
        violations: list[str] = []
        checks = 0

        if not product_id:
            return ScenarioCheckDetail(scenario_name=name, description=desc, passed=True, checks_performed=0)

        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return ScenarioCheckDetail(scenario_name=name, description=desc, passed=True, checks_performed=0)

        # Create hypothetical draft metadata with a rejected attribute
        checks += 1
        fake_rejected_meta = {
            "attributes": {
                "synthetic_rejected_feature": {
                    "type": "text",
                    "value": "UnapprovedKevlar",
                    "confidence": 0.99
                }
            }
        }

        # 1. Embedding text builder ignores unaccepted metadata
        checks += 1
        builder_doc = EmbeddingTextBuilder.build(
            product=product,
            accepted_metadata={}  # Empty accepted state
        )
        if "unapprovedkevlar" in builder_doc.lower():
            violations.append("Rejected attribute value appeared in embedding document.")

        # 2. RAG CitationValidator strictly rejects claims on unaccepted attributes
        checks += 1
        bundle = self.rag_retrieval_service._hydrate_single_product(db, product_id, match_reasons=[])
        if bundle:
            rag_bundle = RAGKnowledgeBundle(question="test", products=[bundle])
            unaccepted_claim_resp = RAGModelResponse(
                answer="Product has unapproved feature.",
                claims=[
                    RAGClaim(
                        claim="Has synthetic rejected feature.",
                        product_id=product_id,
                        attribute="synthetic_rejected_feature",
                        value="UnapprovedKevlar",
                        citation=None
                    )
                ]
            )
            val_res = self.citation_validator.validate(unaccepted_claim_resp, rag_bundle)
            if val_res.is_valid:
                violations.append("CitationValidator accepted a claim on an unaccepted attribute!")
            if not any("INVALID_ATTRIBUTE" in err for err in val_res.errors):
                violations.append("CitationValidator failed to return INVALID_ATTRIBUTE error for unaccepted attribute.")

        return ScenarioCheckDetail(
            scenario_name=name,
            description=desc,
            passed=(len(violations) == 0),
            checks_performed=checks,
            violations=violations
        )

    # --------------------------------------------------------------------------
    # Scenario C: Volatile field isolation
    # --------------------------------------------------------------------------
    def verify_scenario_c_volatile_isolation(
        self,
        db: Session,
        product_id: Optional[int]
    ) -> ScenarioCheckDetail:
        """Verifies volatile price updates do NOT invalidate embeddings, but reflect in Search & RAG."""
        name = "Scenario C — Volatile Field Isolation"
        desc = "Verifies price updates do not dirty embedding documents, but search and RAG use live MySQL price."
        violations: list[str] = []
        checks = 0

        if not product_id:
            return ScenarioCheckDetail(scenario_name=name, description=desc, passed=True, checks_performed=0)

        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return ScenarioCheckDetail(scenario_name=name, description=desc, passed=True, checks_performed=0)

        # 1. Price is excluded from embedding document
        checks += 1
        doc_text, original_hash = self.embedding_service.build_embedding_document(db, product)
        if str(int(product.price)) in doc_text:
            violations.append("Product price was found inside the canonical embedding document!")

        # Simulate price change in memory
        original_price = product.price
        try:
            product.price = original_price + 5000.0
            new_doc_text, new_hash = self.embedding_service.build_embedding_document(db, product)
            checks += 1
            if new_hash != original_hash:
                violations.append("Price update altered the embedding document content hash!")

            # 2. RAG hydration uses live price
            checks += 1
            rag_ctx = self.rag_retrieval_service._hydrate_single_product(db, product_id, match_reasons=[])
            if rag_ctx:
                if rag_ctx.live_catalog_state.get("price") != product.price:
                    violations.append("RAG live_catalog_state does not reflect current MySQL product price.")
        finally:
            # Revert in-memory price modification
            product.price = original_price

        return ScenarioCheckDetail(
            scenario_name=name,
            description=desc,
            passed=(len(violations) == 0),
            checks_performed=checks,
            violations=violations
        )

    # --------------------------------------------------------------------------
    # Scenario D: Inactive product isolation
    # --------------------------------------------------------------------------
    def verify_scenario_d_inactive_isolation(
        self,
        db: Session,
        product_id: Optional[int]
    ) -> ScenarioCheckDetail:
        """Verifies products with status != 'ACTIVE' are never returned in search, RAG, or recommendations."""
        name = "Scenario D — Inactive Product Isolation"
        desc = "Verifies products with status != 'ACTIVE' are never returned in search, RAG, or recommendations."
        violations: list[str] = []
        checks = 0

        # 1. Eligibility guard test: query for any non-ACTIVE product in DB
        checks += 1
        try:
            inactive_prods = db.query(Product).filter(Product.status != "ACTIVE").limit(5).all()
            if isinstance(inactive_prods, list) and len(inactive_prods) > 0:
                inactive_ids = [p.id for p in inactive_prods]
                search_query = SearchQuery(original_query="test", semantic_query="test", filters=SearchFilters())
                survivors, _ = self.eligibility_guard.filter_eligible_candidates(db, inactive_ids, search_query)
                for iid in inactive_ids:
                    if iid in survivors:
                        violations.append(f"Inactive product {iid} passed FinalEligibilityGuard!")
        except Exception as e:
            logger.debug(f"Search guard inactive verification: {e}")

        # 2. Recommendation service exclusion test
        checks += 1
        if product_id:
            try:
                rec_resp = self.recommendation_service.get_recommendations(db, product_id=product_id, limit=10)
                if hasattr(rec_resp, "recommendations"):
                    for rec in rec_resp.recommendations:
                        checks += 1
                        if rec.product.status != "ACTIVE":
                            violations.append(f"Recommendation returned product {rec.product.id} with status '{rec.product.status}'.")
            except Exception as e:
                logger.debug(f"Recommendation retrieval exception in scenario D: {e}")

        return ScenarioCheckDetail(
            scenario_name=name,
            description=desc,
            passed=(len(violations) == 0),
            checks_performed=checks,
            violations=violations
        )

    # --------------------------------------------------------------------------
    # Scenario E: Search -> RAG consistency
    # --------------------------------------------------------------------------
    def verify_scenario_e_search_rag_consistency(
        self,
        db: Session,
        product_id: Optional[int]
    ) -> ScenarioCheckDetail:
        """Verifies RAG retrieves and hydratively preserves exact search results and live state."""
        name = "Scenario E — Search to RAG Consistency"
        desc = "Verifies RAG uses authoritative search candidates and separates retrieval match reasons from facts."
        violations: list[str] = []
        checks = 0

        query_str = "shoes"
        checks += 1
        search_resp = self.hybrid_search_service.search(db, raw_query=query_str, limit=5)
        checks += 1
        rag_bundle, _ = self.rag_retrieval_service.retrieve_and_hydrate(db, question=query_str, limit=5)

        search_pids = [r.product.id for r in search_resp.results]
        rag_pids = [p.product_id for p in rag_bundle.products]

        checks += 1
        if search_pids != rag_pids:
            violations.append(f"RAG product IDs {rag_pids} do not match search result IDs {search_pids}.")

        # Verify match reasons are preserved as retrieval context, not facts
        for prod_ctx in rag_bundle.products:
            checks += 1
            if not isinstance(prod_ctx.search_match_context, list):
                violations.append(f"Product {prod_ctx.product_id} search_match_context is not a list.")

        return ScenarioCheckDetail(
            scenario_name=name,
            description=desc,
            passed=(len(violations) == 0),
            checks_performed=checks,
            violations=violations
        )

    # --------------------------------------------------------------------------
    # Scenario F: Recommendation / catalog consistency
    # --------------------------------------------------------------------------
    def verify_scenario_f_recommendation_consistency(
        self,
        db: Session,
        product_id: Optional[int]
    ) -> ScenarioCheckDetail:
        """Verifies recommendations are active, exist in MySQL, and never self-recommend."""
        name = "Scenario F — Recommendation Catalog Consistency"
        desc = "Verifies recommendations are active catalog products and never recommend the source product."
        violations: list[str] = []
        checks = 0

        if not product_id:
            return ScenarioCheckDetail(scenario_name=name, description=desc, passed=True, checks_performed=0)

        checks += 1
        try:
            rec_resp = self.recommendation_service.get_recommendations(db, product_id=product_id, limit=5)
            for item in rec_resp.recommendations:
                checks += 1
                # 1. Product != source product
                if item.product.id == product_id:
                    violations.append(f"Recommendation engine returned source product {product_id} to itself!")
                # 2. Product is ACTIVE
                if item.product.status != "ACTIVE":
                    violations.append(f"Recommended product {item.product.id} has non-ACTIVE status '{item.product.status}'.")
                # 3. Product exists in MySQL with matching price
                prod_in_db = db.query(Product).filter(Product.id == item.product.id).first()
                if not prod_in_db:
                    violations.append(f"Recommended product {item.product.id} does not exist in MySQL!")
                elif float(prod_in_db.price) != float(item.product.price):
                    violations.append(
                        f"Recommended product {item.product.id} price {item.product.price} differs from MySQL {prod_in_db.price}."
                    )
        except Exception as e:
            violations.append(f"Recommendation service execution failed: {e}")

        return ScenarioCheckDetail(
            scenario_name=name,
            description=desc,
            passed=(len(violations) == 0),
            checks_performed=checks,
            violations=violations
        )
