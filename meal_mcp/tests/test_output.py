"""v1.2.2: smaller tool results. Empty fields are left out, get_recipes has a short form above 5 recipes."""

from db.models import Ingredient, Recipe
from services.measure_service import short_unit
from services.nutrition_service import CALCULATION_NOTE, NutritionService
from services.output import without_empty
from services.recipe_service import RecipeService
from services.substitution_service import SubstitutionService
from tests.test_compare import FakeUSDA
from tests.test_substitutions import build_session, seed_recipe
from tests.test_v1_1 import session_with_variant


def test_without_empty_keeps_false_and_zero():
    assert without_empty({"a": None, "b": [], "c": {}, "d": False, "e": 0, "f": "x"}) == {"d": False, "e": 0, "f": "x"}


def test_list_rows_leave_out_empty_fields():
    session = session_with_variant()
    rows = {row["mealdb_id"]: row for row in RecipeService(session).list_recipes()}
    assert rows["test-1"] == {
        "mealdb_id": "test-1", "name": "Chicken Curry", "category": "Main", "area": "Test",
        "ingredient_count": 2, "variant_ids": ["test-1-v1"],
    }
    assert rows["test-1-v1"]["parent_mealdb_id"] == "test-1"
    assert "variant_ids" not in rows["test-1-v1"]


def test_get_recipes_is_full_up_to_five_recipes():
    session = build_session()
    seed_recipe(session)
    result = RecipeService(session).get_recipes(["test-1", "nope"])
    assert result["compact"] is False
    assert result["missing"] == ["nope"]
    recipe = result["recipes"][0]
    assert recipe["instructions"] == "Cook all ingredients."
    assert recipe["ingredients"][0] == {"position": 1, "name": "Chicken", "measure": "100 g", "estimated_grams": 100.0}


def test_get_recipes_is_compact_above_five_recipes():
    session = build_session()
    for number in range(6):
        recipe = Recipe(mealdb_id=str(number), name=f"R{number}", instructions="Long text.", image_url="http://x/y.jpg")
        recipe.ingredients.append(Ingredient(position=1, name="Salt", normalized_name="salt", measure="1 tsp", estimated_grams=5.0))
        session.add(recipe)
    session.commit()
    service = RecipeService(session)
    result = service.get_recipes([str(number) for number in range(6)])
    assert result["compact"] is True
    assert "missing" not in result
    assert result["recipes"][0] == {
        "mealdb_id": "0", "name": "R0", "ingredient_count": 1,
        "ingredients": [{"position": 1, "name": "Salt", "measure": "1 tsp"}],
    }
    assert "instructions" in service.get_recipes(["0", "1", "2", "3", "4", "5"], compact=False)["recipes"][0]


async def test_nutrition_states_the_calculation_note_once():
    session = session_with_variant()
    service = NutritionService(session)
    service.usda = FakeUSDA()
    await service.enrich_recipes(["test-1", "test-1-v1"])
    result = service.get_nutrition(["test-1", "test-1-v1"])
    assert result["calculation_note"] == CALCULATION_NOTE
    for recipe in result["recipes"]:
        assert not {"calculation_note", "covered_ingredients", "servings", "per_serving"} & set(recipe)
        assert recipe["ingredient_breakdown"]
    assert "calculation_note" not in service.get_nutrition(["test-1"], compact=True)


def test_portion_text_leaves_out_the_note_in_brackets():
    assert short_unit({"unit": 'medium (2-1/2" dia)'}) == "medium"
    assert short_unit({"unit": "cup, chopped"}) == "cup, chopped"


def test_adapted_rows_do_not_repeat_the_rule():
    session = build_session()
    seed_recipe(session)
    service = SubstitutionService(session)
    service.add_substitutions([{"source_ingredient": "milk", "target_ingredient": "oat milk", "reason": "Plant milk", "tags": ["vegan"]}])
    result = service.adapt_recipes(["test-1"])
    milk = result["adapted_recipes"][0]["ingredients"][1]
    assert milk["name"] == "oat milk" and milk["quantity"]["status"] == "adjusted"
    assert not {"substitution", "normalized_name"} & set(milk)
    assert result["adapted_recipes"][0]["changes"][0]["reason"] == "Plant milk"
    assert "missing_recipes" not in result


def test_find_substitutions_without_ingredients_lists_all_rules():
    session = build_session()
    service = SubstitutionService(session)
    service.add_substitutions([
        {"source_ingredient": "milk", "target_ingredient": "oat milk", "reason": "Plant milk", "confidence": 0.9, "tags": ["vegan"]},
        {"source_ingredient": "butter", "target_ingredient": "margarine", "reason": "Fat", "confidence": 0.8, "tags": ["vegetarian"]},
    ])
    everything = service.find_substitutions()
    assert {source: [row["target_ingredient"] for row in rows] for source, rows in everything.items()} == {
        "butter": ["margarine"], "milk": ["oat milk"],
    }
    # Constraints filter the full list too; an ingredient without matching rules is left out.
    assert list(service.find_substitutions(constraints={"diet": "vegan"})) == ["milk"]
    assert service.find_substitutions(["cheese"]) == {"cheese": []}
