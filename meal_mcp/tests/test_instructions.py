from db.models import Recipe
from services.instruction_service import InstructionService, mentioned_terms
from services.variant_service import VariantService
from tests.test_substitutions import build_session
from tests.test_variants import adapted


def saved_variant(session) -> str:
    return VariantService(session).save_variants([adapted(session)])["saved"][0]["mealdb_id"]


def test_request_contains_changes_terms_and_guidelines():
    session = build_session()
    mealdb_id = saved_variant(session)
    result = InstructionService(session).rewrite_requests([mealdb_id])
    assert result["status"] == "rewrite_required"
    assert result["next_tool"] == "save_rewritten_instructions"
    assert result["guidelines"]
    request = result["requests"][0]
    assert request["current_instructions"] == "Cook all ingredients."
    assert request["replaced_terms"] == ["chicken", "milk"]
    assert [(change["source"], change["target"]) for change in request["changes"]] == [
        ("Chicken", "tempeh"), ("Milk", "oat milk"),
    ]


def test_rewrite_is_stored_as_llm_text_and_original_is_unchanged():
    session = build_session()
    mealdb_id = saved_variant(session)
    service = InstructionService(session)
    result = service.save_rewrites([{"mealdb_id": mealdb_id, "instructions": "Fry the tempeh for 8 minutes, add oat milk."}])
    assert result["status"] == "saved"
    assert result["warnings"] == []
    variant = result["saved"][0]
    assert variant["instructions"] == "Fry the tempeh for 8 minutes, add oat milk."
    assert variant["instructions_source"] == "llm"
    assert session.query(Recipe).filter_by(mealdb_id="test-1").one().instructions == "Cook all ingredients."


def test_replaced_ingredient_still_mentioned_gives_warning():
    session = build_session()
    mealdb_id = saved_variant(session)
    result = InstructionService(session).save_rewrites([
        {"mealdb_id": mealdb_id, "instructions": "Fry the tempeh like chicken breasts, add the milk."},
    ])
    assert result["warnings"][0]["still_mentioned"] == ["chicken", "milk"]


def test_rewritten_variant_is_skipped_unless_forced():
    session = build_session()
    mealdb_id = saved_variant(session)
    service = InstructionService(session)
    service.save_rewrites([{"mealdb_id": mealdb_id, "instructions": "Fry the tempeh."}])
    assert service.rewrite_requests([mealdb_id])["status"] == "nothing_to_rewrite"
    assert service.rewrite_requests([mealdb_id], force=True)["status"] == "rewrite_required"


def test_original_and_unknown_recipes_are_rejected():
    session = build_session()
    saved_variant(session)
    service = InstructionService(session)
    result = service.save_rewrites([
        {"mealdb_id": "test-1", "instructions": "Changed."},
        {"mealdb_id": "missing", "instructions": "Changed."},
        {"mealdb_id": "test-1-v1", "instructions": "  "},
    ])
    assert result["status"] == "nothing_saved"
    assert [error["mealdb_id"] for error in result["errors"]] == ["test-1", "missing", "test-1-v1"]
    assert "Only variants" in service.rewrite_requests(["test-1"])["errors"][0]["reason"]


def test_manual_edit_marks_instructions_as_edited():
    session = build_session()
    mealdb_id = saved_variant(session)
    result = VariantService(session).update_variants([{"mealdb_id": mealdb_id, "instructions": "My own text."}])
    assert result["updated"][0]["instructions_source"] == "edited"


def test_mentioned_terms_matches_words_and_plurals_only():
    assert mentioned_terms("Add the onions and chickpeas.", ["onion", "chicken"]) == ["onion"]


def test_substitute_name_containing_the_replaced_term_is_not_reported():
    assert mentioned_terms("Pour in the oat milk.", ["milk"], keep=["oat milk"]) == []
    assert mentioned_terms("Pour in the oat milk and the milk.", ["milk"], keep=["oat milk"]) == ["milk"]


def test_reworded_substitute_is_not_reported():
    substitutes = ["oat yogurt, plain", "oat cream for cooking"]
    keep = ["oat yogurt, plain", "oat cream for cooking"]
    text = "Stir the plain oat yogurt until smooth, then add the oat cooking cream."
    assert mentioned_terms(text, ["yogurt", "cream"], keep, substitutes) == []
    assert mentioned_terms("Add the yogurt and the cream.", ["yogurt", "cream"], keep, substitutes) == ["yogurt", "cream"]
