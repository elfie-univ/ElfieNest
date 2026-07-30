"""Generate evidence-backed foods for one verified local model."""

from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.planner import FoodPlanner, ModelEvidence
from ai_runtime.food.store import FoodCatalogStore
from ai_runtime.models.capabilities import canonical_display_name, known_capabilities


def generate_model_foods(
    model_reference: str,
    evidence_store: ModelEvidenceStore,
    catalog_store: FoodCatalogStore,
) -> None:
    evidence = ModelEvidence(
        model=model_reference,
        display_name=canonical_display_name(model_reference, model_reference),
        capabilities=frozenset({"text"})
        | known_capabilities(model_reference, model_reference),
        verified=True,
        cost_grade=0,
        local=True,
    )
    evidence_store.merge((evidence,))
    all_evidence = tuple(evidence_store.load().values())
    proposal = FoodPlanner().propose(all_evidence, catalog_store.load())
    catalog_store.save(proposal.catalog)
