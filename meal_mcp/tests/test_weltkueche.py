"""Regression tests from a real run over 51 recipes ("Weltküche", v1.0.0).

Measures, portion weights and expectations come from that protocol (docs/FEHLERANALYSE.md, case 14).
"""

import pytest
from sqlalchemy import select

from db.models import NutritionCache
from repo.recipe_repo import RecipeRepo
from services import nutrition_service
from services.match_service import MatchService
from services.measure_service import (
    estimate_grams, grams_from_portions, ingredient_grams, normalize_ingredient_name, parse_amount, scale_measure,
)
from services.nutrition_service import NutritionService
from services.serving_service import ServingService
from services.substitution_service import SubstitutionService
from services.usda_matching import ALIASES, best_match, search_queries
from services.usda_service import USDAService
from services.variant_service import VariantService
from tests.test_compare import FakeUSDA
from tests.test_substitutions import build_session, seed_recipe
from tests.test_variants import adapted

CUP_OIL = [{"unit": "cup", "grams": 218.0}]
TAHINI = [{"unit": "tablespoon", "grams": 15.0}]
TSP_SALT = [{"unit": "tsp", "grams": 6.0}]
CUCUMBER = [{"unit": "medium", "grams": 201.0}]
FISH = [{"unit": "fillet", "grams": 129.0}]
FILO = [{"unit": "sheet dough", "grams": 19.0}]
BEANS = [{"unit": "racc", "grams": 35.0}]
CASHEWS = [{"unit": "racc", "grams": 30.0}, {"unit": "oz", "grams": 28.0}]
HERB = [{"unit": "sprigs", "grams": 2.2}, {"unit": "guideline amount per item", "grams": 0.3}]


@pytest.mark.parametrize("measure, amount", [
    ("1/2 cup", 0.5), ("1/4 tsp", 0.25), ("1/3 cup", 1 / 3), ("1/2", 0.5), ("1/4", 0.25),
    ("2-1/2 cups", 2.5), ("1 1/2 cups", 1.5), ("1½ kg", 1.5), ("1 ½ tbsp", 1.5), ("¼ cup", 0.25),
    ("1.2 kg", 1.2), ("0,5 l", 0.5), ("12", 12.0), ("2-3 cloves", 2.5),
])
def test_amounts_are_read_completely(measure, amount):
    assert parse_amount(measure)[0] == pytest.approx(amount)


@pytest.mark.parametrize("measure, portions, grams", [
    ("1/2 cup", CUP_OIL, 109.0),
    ("1/4 cup", TAHINI, 60.0),
    ("1/2 tsp", TSP_SALT, 3.0),
    ("1/2", CUCUMBER, 100.5),
    ("2-1/2 cups", [{"unit": "cup", "grams": 237.0}], 592.5),
])
def test_fractions_use_the_fraction_of_a_portion(measure, portions, grams):
    assert ingredient_grams(measure, estimate_grams(measure), portions)[0] == pytest.approx(grams)


@pytest.mark.parametrize("measure, grams", [
    ("2 Lbs", 907.184), ("2 tblsp", 30.0), ("1 tblsp", 15.0), ("2 x 400g", 800.0), ("2 x 400 g", 800.0), ("2x400g", 800.0),
    ("1 x 300ml", 300.0), ("1½ kg", 1500.0), ("400ml can", 400.0),
])
def test_units_and_multiplied_amounts(measure, grams):
    assert estimate_grams(measure) == pytest.approx(grams)


def test_multiplied_mass_is_measured_not_counted_as_fillets():
    assert ingredient_grams("2 x 400g", estimate_grams("2 x 400g"), FISH) == (800.0, "measured")


def test_mixed_fraction_mass_is_measured():
    assert ingredient_grams("1½ kg", estimate_grams("1½ kg"), None) == (1500.0, "measured")


@pytest.mark.parametrize("measure, portions", [
    ("1 Packet", FILO), ("1 can", BEANS), ("1 Can", FILO), ("½ small pack", HERB), ("1/2 bag", HERB), ("12", CASHEWS),
])
def test_containers_and_reference_amounts_are_not_converted(measure, portions):
    assert ingredient_grams(measure, estimate_grams(measure), portions) == (None, None)


def test_real_pieces_still_count():
    assert ingredient_grams("6", estimate_grams("6"), [{"unit": "fruit", "grams": 67.0}])[0] == 402.0


@pytest.mark.parametrize("measure, factor, expected", [
    ("1½ kg", 0.2, "300 g"), ("1/2 cup", 2, "1 cup"), ("1/4 cup", 0.5, "0.12 cup"), ("2 x 400g", 0.5, "400 g"), ("2-1/2 cups", 2, "5 cups"),
])
def test_scaling_keeps_a_readable_measure(measure, factor, expected):
    assert scale_measure(measure, factor) == expected


def test_small_amounts_have_a_typical_weight():
    assert ingredient_grams("Pinch", None, None)[0] == 0.4
    assert ingredient_grams("dash", None, None)[0] == 0.6
    assert ingredient_grams("To taste", None, None) == (None, None)


@pytest.mark.parametrize("food, grams", [
    ("Flour, wheat, all-purpose, enriched, bleached", 374.4),
    ("Rice, white, long grain, unenriched, raw", 554.4),
    ("Peanuts, raw", 439.2),
    ("Oil, vegetable, soybean, refined", 720.0),
    ("Nuts, coconut milk, canned", 720.0),
    ("Milk, whole", 720.0),
    ("Tomato, puree, canned", 720.0),
])
def test_dry_foods_use_a_typical_density(food, grams):
    assert ingredient_grams("3 cups", estimate_grams("3 cups"), [], food)[0] == grams


def test_usda_portion_wins_over_density():
    assert ingredient_grams("1 cup", 240.0, [{"unit": "cup", "grams": 125.0}], "Flour")[0] == 125.0


# Matching


@pytest.mark.parametrize("name, description", [
    ("Shredded Meat", "Beef, chuck for stew, separable lean and fat, choice, cooked, braised"),
    ("Cheese Curds", "Cheese, cheddar"),
    ("Bacon", "Pork, cured, bacon, unprepared"),
    ("Tomato Sauce", "Tomato products, canned, sauce"),
    ("Kidney Beans", "Beans, kidney, all types, mature seeds, canned"),
    ("Oil", "Oil, vegetable, soybean, refined"),
    ("Unsalted Butter", "Butter, without salt"),
    ("Basmati Rice", "Rice, white, long grain, unenriched, raw"),
    ("King Prawns", "Crustaceans, shrimp, raw"),
    ("Egg Plants", "Eggplant, raw"),
    ("Lamb Mince", "Lamb, ground, raw"),
    ("Filo Pastry", "Phyllo dough"),
    ("Beetroot", "Beets, raw"),
    ("Cream", "Cream, fluid, heavy whipping"),
    ("Chilli", "Peppers, hot chili, red, raw"),
])
def test_aliases_from_the_run(name, description):
    assert search_queries(name.lower())[0] == description


@pytest.mark.parametrize("name, first_query", [
    # Second run (02.11), calculate_nutrition with German and USDA-style names
    ("Tofu", "Tofu, raw, regular, prepared with calcium sulfate"),
    ("soy milk", "Soymilk, original and vanilla, unfortified"),
    ("white rice", "Rice, white, long-grain, regular, raw, enriched"),
    ("wheat flour", "Wheat flour, white, all-purpose, enriched, bleached"),
    ("Schweinehackfleisch", "ground pork"),
    ("Gemüsebrühe", "Soup, vegetable broth, ready to serve"),
    ("Sojasoße", "soy sauce"),
    ("Speisestärke", "cornstarch"),
    ("Rapsöl", "Oil, canola"),
    ("tofu, firm", "Tofu, raw, firm, prepared with calcium sulfate"),
    ("lasagna noodles, dry", "Pasta, dry, enriched"),
    ("chicken, cooked", "chicken cooked"),
])
def test_names_from_the_second_run(name, first_query):
    assert search_queries(normalize_ingredient_name(name))[0] == first_query


EGGPLANT = [
    {"unit": "eggplant, unpeeled (approx 1-1/4 lb)", "grams": 548.0},
    {"unit": "eggplant, peeled (yield from 1-1/4 lb)", "grams": 458.0},
    {"unit": "cup, cubes", "grams": 82.0},
]
YELLOW_PEPPER = [{"unit": "strips", "grams": 5.2}, {"unit": "pepper, large (3-3/4\" long, 3\" dia)", "grams": 186.0}]
ROMAINE = [{"unit": "cup shredded", "grams": 47.0}, {"unit": "leaf inner", "grams": 6.0}, {"unit": "head", "grams": 626.0}]


@pytest.mark.parametrize("measure, portions, grams", [
    ("2 large", EGGPLANT, 1096.0),  # the note "(approx 1-1/4 lb)" is no mass unit
    ("2", YELLOW_PEPPER, 372.0),  # two peppers, not two strips
    ("1", ROMAINE, 626.0),
    ("4 leaves", ROMAINE, 24.0),
])
def test_bare_counts_mean_whole_pieces(measure, portions, grams):
    assert grams_from_portions(measure, portions)[0] == grams


def test_aliases_are_lower_case():
    assert all(name == name.lower() for name in ALIASES)


def test_same_description_prefers_the_entry_with_portion_weights():
    foods = [
        {"fdcId": 1, "dataType": "Foundation", "description": "Beets, raw"},
        {"fdcId": 2, "dataType": "SR Legacy", "description": "Beets, raw"},
    ]
    assert best_match("Beets, raw", foods)["fdcId"] == 2


FOOD_WITHOUT_ENERGY = {"fdcId": 748278, "dataType": "Foundation", "description": "Oil, canola", "foodNutrients": []}
FOOD_WITH_ENERGY = {
    "fdcId": 172336, "dataType": "SR Legacy", "description": "Oil, canola",
    "foodNutrients": [{"nutrientName": "Energy", "value": 884, "unitName": "KCAL"}],
}


async def test_food_without_energy_is_not_chosen():
    service = USDAService()

    async def candidates(client, query):
        return [FOOD_WITHOUT_ENERGY, FOOD_WITH_ENERGY]

    service._candidates = candidates
    assert (await service._find(None, "oil canola"))["fdcId"] == 172336


class EmptyEnergyUSDA(FakeUSDA):
    async def get_nutrients_bulk(self, ingredients):
        return {"matched": [{
            "normalized_name": item["normalized_name"], "source_name": item["source_name"], "usda_fdc_id": "1",
            "matched_name": "x", "calories_per_100g": None, "protein_per_100g": None,
            "fat_per_100g": 81.5, "carbs_per_100g": None, "portions": [],
        } for item in ingredients], "missing": [], "errors": {}}


async def test_missing_energy_is_uncovered_not_zero():
    session = build_session()
    seed_recipe(session)
    service = NutritionService(session)
    service.usda = EmptyEnergyUSDA()
    await service.enrich_recipes(["test-1"])
    summary = service.get_nutrition(["test-1"])["recipes"][0]
    assert summary["calories"] == 0
    assert summary["coverage"]["covered"] == 0
    assert {row["reason"] for row in summary["uncovered_ingredients"]} == {"calories_missing"}


async def test_cached_food_without_energy_is_looked_up_again():
    session = build_session()
    seed_recipe(session)
    service = NutritionService(session)
    service.usda = EmptyEnergyUSDA()
    await service.enrich_recipes(["test-1"])
    service.usda = FakeUSDA()
    result = await service.enrich_recipes(["test-1"])
    assert result["ingredients_loaded_from_usda"] == 2
    assert session.scalar(select(NutritionCache).where(NutritionCache.normalized_name == "chicken")).calories_per_100g == 200.0


async def test_manual_match_without_energy_is_refused():
    session = build_session()
    matches = MatchService(session)
    matches.usda = EmptyEnergyUSDA()
    result = await matches.set_matches([{"ingredient": "butter", "fdc_id": "789828"}])
    assert result["status"] == "nothing_updated"
    assert "no energy value" in result["errors"][0]["reason"]


# compare_nutrition


async def test_compare_names_the_real_cause_for_an_unconvertible_original():
    session = build_session()
    RecipeRepo(session).save_bulk([{
        "idMeal": "1", "strMeal": "Curry", "strInstructions": "Cook.",
        "strIngredient1": "chicken", "strMeasure1": "some",
        "strIngredient2": "milk", "strMeasure2": "100 ml",
    }])
    VariantService(session).save_variants([{
        "source_mealdb_id": "1", "name": "Vegan curry", "constraints": {"diet": "vegan"},
        "ingredients": [
            {"position": 1, "name": "tempeh", "measure": "900 g"},
            {"position": 2, "name": "oat milk", "measure": "100 ml"},
        ],
    }])
    service = NutritionService(session)
    service.usda = FakeUSDA()
    comparison = (await service.compare_variants(["1-v1"]))["comparisons"][0]
    assert comparison["comparable"] is False
    assert "amount 'some' of original chicken cannot be converted" in comparison["notes"][0]
    assert "no nutrition data" not in comparison["notes"][0]


# Large runs


def many_recipes(session, count=7):
    RecipeRepo(session).save_bulk([{
        "idMeal": str(number), "strMeal": f"Recipe {number}", "strInstructions": "Long text. " * 50,
        "strMealThumb": "https://example.invalid/x.jpg",
        "strIngredient1": "chicken", "strMeasure1": "100 g",
        "strIngredient2": "milk", "strMeasure2": "100 ml",
    } for number in range(count)])
    return [str(number) for number in range(count)]


def test_adapt_is_compact_above_five_recipes_and_can_be_saved():
    session = build_session()
    ids = many_recipes(session)
    service = SubstitutionService(session)
    service.add_substitutions([{"source_ingredient": "chicken", "target_ingredient": "tempeh", "tags": ["vegan"]}])
    result = service.adapt_recipes(ids)
    assert result["compact"] is True
    item = result["adapted_recipes"][0]
    assert "instructions" not in item
    assert set(item["ingredients"][0]) == {"position", "name", "measure"}
    assert item["ingredients"][0]["name"] == "tempeh"

    saved = VariantService(session).save_variants([item])
    assert saved["status"] == "saved"
    variant = RecipeRepo(session).get_bulk([saved["saved"][0]["mealdb_id"]])[0]
    assert variant.instructions == variant.parent.instructions
    assert variant.changes[0]["target"] == "tempeh"


def test_compact_can_be_chosen():
    session = build_session()
    ids = many_recipes(session)
    service = SubstitutionService(session)
    assert "instructions" in service.adapt_recipes(ids, compact=False)["adapted_recipes"][0]
    assert "instructions" not in service.adapt_recipes(ids[:1], compact=True)["adapted_recipes"][0]
    assert service.adapt_recipes(ids[:5])["compact"] is False


def test_compact_output_is_much_smaller():
    session = build_session()
    ids = many_recipes(session)
    service = SubstitutionService(session)
    assert len(str(service.adapt_recipes(ids))) * 2 < len(str(service.adapt_recipes(ids, compact=False)))


async def test_nutrition_and_compare_are_compact_above_five():
    session = build_session()
    ids = many_recipes(session)
    service = NutritionService(session)
    service.usda = FakeUSDA()
    await service.enrich_recipes(ids)
    summary = service.get_nutrition(ids)["recipes"][0]
    assert "ingredient_breakdown" not in summary
    assert summary["calories"] == 260.0
    assert "ingredient_breakdown" in service.get_nutrition(ids, compact=False)["recipes"][0]

    VariantService(session).save_variants([
        {"source_mealdb_id": mealdb_id, "name": "v", "ingredients": [
            {"position": 1, "name": "tempeh", "measure": "100 g"}, {"position": 2, "name": "milk", "measure": "100 ml"},
        ]} for mealdb_id in ids
    ])
    result = await service.compare_variants(ids)
    assert result["compact"] is True
    assert result["comparisons"][0]["change_effects"] == []
    assert "uncovered_ingredients" not in result["comparisons"][0]


async def test_enrichment_stops_at_the_time_budget_and_continues(monkeypatch):
    monkeypatch.setattr(nutrition_service.settings, "enrich_time_budget_seconds", 0.0)
    session = build_session()
    RecipeRepo(session).save_bulk([{
        "idMeal": "1", "strMeal": "Big", **{f"strIngredient{n}": f"food {n}" for n in range(1, 21)},
        **{f"strMeasure{n}": "1 g" for n in range(1, 21)},
    }])
    service = NutritionService(session)

    class Everything(FakeUSDA):
        async def get_nutrients_bulk(self, ingredients):
            return {"matched": [{
                "normalized_name": item["normalized_name"], "source_name": item["source_name"], "usda_fdc_id": "1",
                "matched_name": "x", "calories_per_100g": 100.0, "protein_per_100g": 1.0,
                "fat_per_100g": 1.0, "carbs_per_100g": 1.0, "portions": [],
            } for item in ingredients], "missing": [], "errors": {}}

    service.usda = Everything()
    first = await service.enrich_recipes(["1"])
    assert first["complete"] is False
    assert first["ingredients_loaded_from_usda"] == nutrition_service.ENRICH_BATCH_SIZE
    assert first["remaining_ingredients"] == 20 - nutrition_service.ENRICH_BATCH_SIZE
    assert first["status"] == "partial_success"
    assert first["next_step"]

    second = await service.enrich_recipes(["1"])
    assert second["complete"] is True
    assert second["ingredients_from_cache"] == nutrition_service.ENRICH_BATCH_SIZE
    assert second["next_step"] is None


async def test_ingredients_without_match_wait_at_the_end(monkeypatch):
    monkeypatch.setattr(nutrition_service, "recent_misses", {"food 1": 0.0})
    monkeypatch.setattr(nutrition_service.time, "monotonic", lambda: 1.0)
    service = NutritionService(build_session())
    seen = []

    class Recorder(FakeUSDA):
        async def get_nutrients_bulk(self, ingredients):
            seen.extend(item["normalized_name"] for item in ingredients)
            return {"matched": [], "missing": [], "errors": {}}

    service.usda = Recorder()
    await service._lookup_in_batches([
        {"normalized_name": "food 1", "source_name": "a"}, {"normalized_name": "food 2", "source_name": "b"},
    ], False)
    assert seen == ["food 2", "food 1"]


# Hidden ingredients


def saffron_recipe(session):
    RecipeRepo(session).save_bulk([{
        "idMeal": "9", "strMeal": "Biryani", "strInstructions": "Marinate the lamb. Cook the prawns in stock.",
        "strIngredient1": "Lamb", "strMeasure1": "500 g",
        "strIngredient2": "Saffron", "strMeasure2": "½ tsp dissolved in ½ cup warm milk",
    }])


def test_ingredients_in_measures_and_instructions_are_reported():
    session = build_session()
    saffron_recipe(session)
    service = SubstitutionService(session)
    service.add_substitutions([
        {"source_ingredient": "milk", "target_ingredient": "oat milk", "tags": ["vegan"]},
        {"source_ingredient": "prawns", "target_ingredient": "tofu", "tags": ["vegan"]},
        {"source_ingredient": "lamb", "target_ingredient": "seitan", "tags": ["vegan"]},
    ])
    result = service.adapt_recipes(["9"])
    found = {(row["term"], row["where"], row["substitute"]) for row in result["hidden_ingredients"]}
    assert found == {
        ("milk", "measure of Saffron", "oat milk"),
        ("prawns", "instructions", "tofu"),
    }
    assert result["hidden_note"]
    assert result["adapted_recipes"][0]["hidden_ingredients"]


def test_no_hidden_ingredients_no_note():
    session = build_session()
    seed_recipe(session)
    service = SubstitutionService(session)
    result = service.adapt_recipes(["test-1"])
    assert result["hidden_ingredients"] == []
    assert "hidden_note" not in result


def test_constraint_excluded_substitute_is_not_suggested_as_hidden():
    session = build_session()
    saffron_recipe(session)
    service = SubstitutionService(session)
    service.add_substitutions([{"source_ingredient": "milk", "target_ingredient": "almond milk", "tags": ["vegan"]}])
    assert service.adapt_recipes(["9"], {"dislikes": ["almond milk"]})["hidden_ingredients"] == []


# Servings use the same parser.


def test_scale_recipes_with_fractions():
    session = build_session()
    RecipeRepo(session).save_bulk([{
        "idMeal": "1", "strMeal": "Soup", "strIngredient1": "Oil", "strMeasure1": "1/2 cup",
        "strIngredient2": "Clams", "strMeasure2": "1½ kg",
    }])
    service = ServingService(session)
    service.set_servings([{"mealdb_id": "1", "servings": 2}])
    rows = service.scale([{"mealdb_id": "1", "servings": 4}])["recipes"][0]["ingredients"]
    assert [row["scaled_measure"] for row in rows] == ["1 cup", "3 kg"]


def test_variant_helper_still_works():
    session = build_session()
    assert VariantService(session).save_variants([adapted(session)])["status"] == "saved"


def test_cup_of_cream_is_liquid_not_whipped():
    portions = [{"unit": "cup, whipped", "grams": 120.0}, {"unit": "cup, fluid (yields 2 cups whipped)", "grams": 238.0}]
    assert ingredient_grams("¾ cup", 180.0, portions)[0] == 178.5


def test_plain_cup_wins_over_a_prepared_form():
    portions = [{"unit": "cup, chopped", "grams": 160.0}, {"unit": "cup", "grams": 100.0}]
    assert ingredient_grams("1 cup", 240.0, portions)[0] == 100.0
