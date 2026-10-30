from db.models import Ingredient, Recipe
from repo.nutrition_repo import NutritionRepo
from repo.substitution_repo import SubstitutionRepo
from services.measure_service import estimate_grams, measure_kind, normalize_ingredient_name, scale_measure
from services.substitution_service import SubstitutionService
from tests.test_substitutions import build_session


def seed(session, measures: dict[str, str], substitutions: list[dict], portions: dict | None = None):
    recipe = Recipe(mealdb_id="q-1", name="Test", instructions="Cook.")
    for position, (name, measure) in enumerate(measures.items(), start=1):
        recipe.ingredients.append(Ingredient(
            position=position, name=name, normalized_name=normalize_ingredient_name(name),
            measure=measure, estimated_grams=estimate_grams(measure),
        ))
    session.add(recipe)
    SubstitutionRepo(session).add_bulk(substitutions)
    for name, rows in (portions or {}).items():
        NutritionRepo(session).save_bulk([{
            "normalized_name": name, "source_name": name, "usda_fdc_id": "1", "matched_name": name,
            "calories_per_100g": 100.0, "protein_per_100g": 1.0, "fat_per_100g": 1.0, "carbs_per_100g": 1.0,
            "portions": rows,
        }])
    session.commit()


def adapt(session) -> dict:
    result = SubstitutionService(session).adapt_recipes(["q-1"], {"diet": "vegan"})
    return result, {row["name"]: row for row in result["adapted_recipes"][0]["ingredients"]}


def test_piece_count_becomes_grams_not_pieces():
    session = build_session()
    seed(
        session,
        {"Chicken Breasts": "4"},
        [{"source_ingredient": "chicken breasts", "target_ingredient": "chickpeas", "tags": ["vegan"]}],
        {"chicken breasts": [{"unit": "breast, bone and skin removed", "grams": 174.0}]},
    )
    _, rows = adapt(session)
    chickpeas = rows["chickpeas"]
    assert chickpeas["measure"] == "696 g"
    assert chickpeas["estimated_grams"] == 696.0
    assert chickpeas["quantity"]["status"] == "adjusted"
    assert chickpeas["quantity"]["estimated"] is True
    assert "174" in chickpeas["quantity"]["basis"]


def test_ratio_scales_mass_and_volume_in_their_unit():
    session = build_session()
    seed(
        session,
        {"Butter": "100 g", "Milk": "200 ml"},
        [
            {"source_ingredient": "butter", "target_ingredient": "olive oil", "tags": ["vegan"],
             "quantity_ratio": 0.75, "quantity_note": "Oil is pure fat, butter about 80 %."},
            {"source_ingredient": "milk", "target_ingredient": "oat milk", "tags": ["vegan"]},
        ],
    )
    _, rows = adapt(session)
    assert rows["olive oil"]["measure"] == "75 g"
    assert rows["olive oil"]["quantity"]["note"] == "Oil is pure fat, butter about 80 %."
    assert rows["oat milk"]["measure"] == "200 ml"
    assert rows["oat milk"]["quantity"]["ratio"] == 1.0


def test_unconvertible_amount_is_kept_and_reported():
    session = build_session()
    seed(
        session,
        {"Eggs": "2", "Honey": "to taste"},
        [
            {"source_ingredient": "eggs", "target_ingredient": "flax egg", "tags": ["vegan"]},
            {"source_ingredient": "honey", "target_ingredient": "maple syrup", "tags": ["vegan"]},
        ],
    )
    result, rows = adapt(session)
    assert rows["flax egg"]["measure"] == "2"
    assert rows["flax egg"]["quantity"]["status"] == "unverified"
    assert "enrich_recipes" in rows["flax egg"]["quantity"]["reason"]
    assert [row["ingredient"] for row in result["unverified_quantities"]] == ["Eggs", "Honey"]


def test_set_quantities_updates_existing_rule_and_rejects_bad_ratio():
    session = build_session()
    repo = SubstitutionRepo(session)
    repo.add_bulk([{"source_ingredient": "butter", "target_ingredient": "olive oil"}])
    result = repo.set_quantities([
        {"source_ingredient": "butter", "target_ingredient": "olive oil", "quantity_ratio": 0.8},
        {"source_ingredient": "butter", "target_ingredient": "lard", "quantity_ratio": 1},
        {"source_ingredient": "butter", "target_ingredient": "olive oil", "quantity_ratio": -1},
    ])
    assert result["updated"][0]["quantity_ratio"] == 0.8
    assert result["missing"] == [{"source_ingredient": "butter", "target_ingredient": "lard"}]
    assert len(result["invalid"]) == 1
    assert repo.list_all()[0]["quantity_ratio"] == 0.8


def test_default_ratio_is_one():
    session = build_session()
    created = SubstitutionRepo(session).add_bulk([{"source_ingredient": "a", "target_ingredient": "b"}])["created"][0]
    assert created["quantity_ratio"] == 1.0


def test_measure_helpers():
    assert measure_kind("1.2 kg") == "mass"
    assert measure_kind("2 tbsp") == "volume"
    assert measure_kind("8 cloves") == "piece"
    assert measure_kind("to taste") == "unknown"
    assert scale_measure("1 1/2 cups", 2) == "3 cups"
    assert scale_measure("200 ml", 0.75) == "150 ml"


def test_scale_keeps_text_at_ratio_one_and_uses_grams_below_one_kg():
    assert scale_measure("¾ cup", 1.0) == "¾ cup"
    assert scale_measure("1.2 kg", 0.8) == "960 g"
    assert scale_measure("2 kg", 0.8) == "1.6 kg"
