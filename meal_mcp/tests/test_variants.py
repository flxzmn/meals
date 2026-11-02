from db.models import Recipe
from repo.substitution_repo import SubstitutionRepo
from services.recipe_service import RecipeService
from services.substitution_service import SubstitutionService
from services.variant_service import VariantService
from tests.test_substitutions import build_session, seed_recipe, seed_substitutions

CONSTRAINTS = {"diet": "vegan", "dislikes": ["tofu"]}


def adapted(session) -> dict:
    seed_recipe(session)
    seed_substitutions(SubstitutionRepo(session))
    return SubstitutionService(session).adapt_recipes(["test-1"], CONSTRAINTS)["adapted_recipes"][0]


def test_adapted_recipe_is_saved_as_variant_and_original_is_unchanged():
    session = build_session()
    result = VariantService(session).save_variants([adapted(session)])
    assert result["status"] == "saved"
    variant = result["saved"][0]
    assert variant["mealdb_id"] == "test-1-v1"
    assert variant["parent_mealdb_id"] == "test-1"

    original = session.query(Recipe).filter_by(mealdb_id="test-1").one()
    assert [row.normalized_name for row in original.ingredients] == ["chicken", "milk"]
    assert [row.mealdb_id for row in original.variants] == ["test-1-v1"]


def test_constraints_and_changes_are_stored():
    session = build_session()
    VariantService(session).save_variants([adapted(session)])
    full = RecipeService(session).get_recipes(["test-1-v1"])["recipes"][0]
    assert full["constraints"] == {"diet": "vegan", "dislikes": ["tofu"]}
    assert [(change["type"], change["source"], change["target"]) for change in full["changes"]] == [
        ("substituted", "Chicken", "tempeh"),
        ("substituted", "Milk", "oat milk"),
    ]
    assert full["changes"][0]["reason"] == "vegan"
    assert full["changes"][0]["confidence"] == 0.9
    assert [row["name"] for row in full["ingredients"]] == ["tempeh", "oat milk"]


def test_same_variant_is_not_saved_twice():
    session = build_session()
    item = adapted(session)
    service = VariantService(session)
    service.save_variants([item])
    again = service.save_variants([item])
    assert again["status"] == "existing"
    assert again["saved"] == []
    assert again["existing"][0]["mealdb_id"] == "test-1-v1"


def test_different_variants_get_their_own_ids():
    session = build_session()
    item = adapted(session)
    other = {**item, "ingredients": [{**row, "measure": "150 g"} if row["position"] == 1 else row for row in item["ingredients"]]}
    result = VariantService(session).save_variants([item, other])
    assert [row["mealdb_id"] for row in result["saved"]] == ["test-1-v1", "test-1-v2"]


def test_unknown_source_and_empty_ingredients_are_rejected():
    session = build_session()
    seed_recipe(session)
    result = VariantService(session).save_variants([
        {"source_mealdb_id": "missing", "ingredients": [{"name": "tempeh"}]},
        {"source_mealdb_id": "test-1", "ingredients": []},
    ])
    assert result["status"] == "nothing_saved"
    assert [error["source_mealdb_id"] for error in result["errors"]] == ["missing", "test-1"]


def test_variant_can_be_edited_and_changes_are_recomputed():
    session = build_session()
    service = VariantService(session)
    service.save_variants([adapted(session)])
    result = service.update_variants([{
        "mealdb_id": "test-1-v1",
        "name": "Tempeh Curry",
        "instructions": "Fry the tempeh for 8 minutes.",
        "ingredients": [
            {"position": 1, "name": "tempeh", "measure": "150 g"},
            {"position": 2, "name": "oat milk", "measure": "100 ml"},
            {"position": 3, "name": "Spinach", "measure": "50 g"},
        ],
    }])
    assert result["status"] == "updated"
    variant = result["updated"][0]
    assert variant["name"] == "Tempeh Curry"
    assert variant["updated_at"] is not None
    assert [(change["type"], change["target"], change["target_measure"]) for change in variant["changes"]] == [
        ("substituted", "tempeh", "150 g"),
        ("substituted", "oat milk", "100 ml"),
        ("added", "Spinach", "50 g"),
    ]
    assert variant["changes"][0]["reason"] == "vegan"  # kept from adapt_recipes
    assert variant["ingredients"][0]["estimated_grams"] == 150.0


def test_original_recipe_cannot_be_edited():
    session = build_session()
    seed_recipe(session)
    result = VariantService(session).update_variants([{"mealdb_id": "test-1", "name": "Changed"}])
    assert result["status"] == "nothing_updated"
    assert "Original recipes cannot be changed" in result["errors"][0]["reason"]
    assert session.query(Recipe).filter_by(mealdb_id="test-1").one().name == "Chicken Curry"


def test_variants_are_listed_per_original():
    session = build_session()
    VariantService(session).save_variants([adapted(session)])
    listed = {row["mealdb_id"]: row for row in RecipeService(session).list_recipes()}
    assert listed["test-1"]["variant_ids"] == ["test-1-v1"]
    assert listed["test-1-v1"]["parent_mealdb_id"] == "test-1"


def test_deleting_variant_keeps_original_and_deleting_original_removes_variants():
    session = build_session()
    service = VariantService(session)
    item = adapted(session)
    service.save_variants([item])
    recipes = RecipeService(session)
    assert recipes.delete_recipes(["test-1-v1"])["deleted"] == ["test-1-v1"]
    assert session.query(Recipe).filter_by(mealdb_id="test-1").one()

    service.save_variants([item])
    result = recipes.delete_recipes(["test-1"])
    assert result["deleted_variants"] == ["test-1-v1"]
    assert session.query(Recipe).count() == 0
