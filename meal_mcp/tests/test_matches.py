import httpx
import pytest

from config.settings import settings
from db.models import Recipe
from repo.nutrition_repo import NutritionRepo
from repo.recipe_repo import RecipeRepo
from services.match_service import MatchService
from services.nutrition_service import NutritionService
from services.usda_matching import search_queries, translate
from services.usda_service import USDAService
from tests.test_db import build_session

# USDA fake: two fenugreek foods, found by search; details by /food/<id>.
FOODS = {
    "1": {"fdcId": 1, "description": "Spices, fenugreek seed", "dataType": "SR Legacy",
          "foodNutrients": [{"nutrientName": "Energy", "unitName": "KCAL", "value": 323},
                            {"nutrientName": "Protein", "unitName": "G", "value": 23.0}]},
    "2": {"fdcId": 2, "description": "Fenugreek leaves, dried", "dataType": "SR Legacy",
          "foodNutrients": [{"nutrientName": "Energy", "unitName": "KCAL", "value": 280},
                            {"nutrientName": "Protein", "unitName": "G", "value": 21.0}]},
}


def detail(food: dict) -> dict:
    """Food detail format: nutrient.name / amount instead of nutrientName / value."""
    return {
        "fdcId": food["fdcId"], "description": food["description"], "dataType": food["dataType"],
        "foodNutrients": [
            {"nutrient": {"name": row["nutrientName"], "unitName": row["unitName"]}, "amount": row["value"]}
            for row in food["foodNutrients"]
        ],
        "foodPortions": [{"amount": 1.0, "modifier": "tsp", "gramWeight": 3.7}],
    }


def handler(request: httpx.Request) -> httpx.Response:
    if "/food/" in request.url.path:
        food = FOODS.get(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, request=request, json=detail(food)) if food else httpx.Response(404, request=request)
    return httpx.Response(200, request=request, json={"foods": list(FOODS.values())})


@pytest.fixture
def services(monkeypatch):
    monkeypatch.setattr(settings, "usda_api_key", "test-key")
    session = build_session()
    usda = USDAService(httpx.MockTransport(handler), retry_delay=0)
    matches = MatchService(session)
    matches.usda = usda
    nutrition = NutritionService(session)
    nutrition.usda = usda
    return session, matches, nutrition


def test_german_and_international_names_are_translated():
    assert translate("Hähnchen") == "chicken"
    assert translate("frischer Knoblauch") == "garlic"
    assert translate("grüne Chilischoten") == "green chili"
    assert translate("parmigiano-reggiano") == "parmesan cheese"
    assert search_queries("courgettes")[0] == "Squash, summer, zucchini, includes skin, raw"
    assert search_queries("zwiebeln")[0] == "Onions, raw"


def test_plain_chickpeas_mean_canned_not_dried():
    assert "canned" in search_queries("chickpeas")[0]
    assert "raw" in search_queries("dried chickpeas")[0]


def test_detail_format_is_extracted():
    values = USDAService()._extract("Fenugreek", "fenugreek", detail(FOODS["2"]))
    assert values["calories_per_100g"] == 280
    assert values["protein_per_100g"] == 21.0


async def test_search_lists_candidates(services):
    _, matches, _ = services
    result = await matches.search_foods(["fenugreek"])
    assert [row["fdc_id"] for row in result["results"]["fenugreek"]] == ["1", "2"]
    assert result["results"]["fenugreek"][1]["calories_per_100g"] == 280


async def test_manual_match_is_loaded_and_kept_on_refresh(services):
    session, matches, nutrition = services
    result = await matches.set_matches([{"ingredient": "Fenugreek", "fdc_id": "2", "note": "Kasuri methi"}])
    assert result["updated"][0]["usda_match"] == "Fenugreek leaves, dried"
    cached = NutritionRepo(session).get_cached_bulk(["fenugreek"])["fenugreek"]
    assert cached.portions == [{"unit": "tsp", "grams": 3.7}]

    RecipeRepo(session).save_bulk([{"idMeal": "1", "strMeal": "Curry", "strIngredient1": "Fenugreek", "strMeasure1": "1 tsp"}])
    await nutrition.enrich_recipes(["1"], refresh=True)
    assert NutritionRepo(session).get_cached_bulk(["fenugreek"])["fenugreek"].usda_fdc_id == "2"
    assert [row["ingredient"] for row in matches.list_matches()] == ["fenugreek"]
    listed = matches.list_matches(["fenugreek"])[0]
    assert listed["source"] == "manual"
    assert listed["note"] == "Kasuri methi"


async def test_rejected_match_is_replaced_and_never_chosen_again(services):
    session, matches, nutrition = services
    RecipeRepo(session).save_bulk([{"idMeal": "1", "strMeal": "Curry", "strIngredient1": "Fenugreek", "strMeasure1": "1 tsp"}])
    await nutrition.enrich_recipes(["1"])
    assert NutritionRepo(session).get_cached_bulk(["fenugreek"])["fenugreek"].usda_fdc_id == "1"

    result = await matches.reject_matches([{"ingredient": "fenugreek", "note": "Recipe means dried leaves"}])
    assert result["rejected"][0]["rejected_fdc_id"] == "1"
    assert result["new_matches"][0]["fdc_id"] == "2"

    await nutrition.enrich_recipes(["1"], refresh=True)
    assert NutritionRepo(session).get_cached_bulk(["fenugreek"])["fenugreek"].usda_fdc_id == "2"
    assert matches.list_matches(["fenugreek"])[0]["rejected_fdc_ids"] == ["1"]


async def test_unknown_food_and_missing_fields_are_errors(services):
    _, matches, _ = services
    result = await matches.set_matches([{"ingredient": "fenugreek", "fdc_id": "999"}, {"ingredient": "salt"}])
    assert result["status"] == "nothing_updated"
    assert len(result["errors"]) == 2


async def test_custom_values_are_stored_counted_and_kept_on_refresh(services):
    session, matches, nutrition = services
    result = await matches.set_matches([{
        "ingredient": "Seitan", "calories_per_100g": 140, "protein_per_100g": 25, "fat_per_100g": 2, "carbs_per_100g": 5,
    }])
    assert result["updated"][0]["fdc_id"] == "custom"
    RecipeRepo(session).save_bulk([{"idMeal": "1", "strMeal": "Curry", "strIngredient1": "Seitan", "strMeasure1": "200 g"}])
    await nutrition.enrich_recipes(["1"], refresh=True)
    summary = nutrition.get_nutrition(["1"])["recipes"][0]
    assert summary["calories"] == 280.0
    assert matches.list_matches(["seitan"])[0]["source"] == "manual"


async def test_invalid_custom_value_is_an_error(services):
    _, matches, _ = services
    result = await matches.set_matches([{"ingredient": "Seitan", "calories_per_100g": -1}])
    assert result["status"] == "nothing_updated"
    assert "negative" in result["errors"][0]["reason"]


async def test_free_ingredients_are_calculated_without_a_recipe(services):
    session, _, nutrition = services
    result = await nutrition.calculate([{"name": "Fenugreek", "measure": "2 tsp"}, {"name": ""}])
    assert result["calories"] == 23.9  # 2 tsp x 3.7 g x 323 kcal / 100 g
    assert result["coverage"]["covered"] == 1
    assert len(result["invalid"]) == 1
    assert session.query(Recipe).count() == 0
