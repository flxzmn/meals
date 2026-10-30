from repo.nutrition_repo import NutritionRepo
from repo.recipe_repo import RecipeRepo
from services.nutrition_service import NutritionService
from tests.test_db import build_session, sample_meal


class FakeUSDA:
    def __init__(self, portions=None):
        self.requested = []
        self.portions = portions or {}

    async def get_nutrients_bulk(self, ingredients):
        self.requested.append([item["normalized_name"] for item in ingredients])
        return {
            "matched": [{
                "normalized_name": item["normalized_name"], "source_name": item["source_name"],
                "usda_fdc_id": "9", "matched_name": f"{item['source_name']}, raw",
                "calories_per_100g": 100.0, "protein_per_100g": 10.0, "fat_per_100g": 1.0, "carbs_per_100g": 1.0,
                "portions": self.portions.get(item["normalized_name"], []),
            } for item in ingredients],
            "missing": [],
            "errors": {},
        }


def service_with_cached_tomato(meal=None, portions=None):
    session = build_session()
    RecipeRepo(session).save_bulk([meal or sample_meal()])
    NutritionRepo(session).save_bulk([{
        "normalized_name": "tomato", "source_name": "Tomato", "usda_fdc_id": "1",
        "matched_name": "Tomato soup", "calories_per_100g": 30.0,
        "protein_per_100g": 1.0, "fat_per_100g": 1.0, "carbs_per_100g": 5.0, "portions": [],
    }])
    service = NutritionService(session)
    service.usda = FakeUSDA(portions)
    return service


async def test_enrich_uses_cache_unless_refresh():
    service = service_with_cached_tomato()
    await service.enrich_recipes(["52771"])
    assert service.usda.requested == [["olive oil"]]

    result = await service.enrich_recipes(["52771"], refresh=True)
    assert service.usda.requested[-1] == ["tomato", "olive oil"]
    assert result["ingredients_from_cache"] == 0
    assert service.nutrition_repo.get_cached_bulk(["tomato"])["tomato"].matched_name == "Tomato, raw"


async def test_nutrition_shows_usda_match_per_ingredient():
    service = service_with_cached_tomato()
    await service.enrich_recipes(["52771"], refresh=True)
    breakdown = service.get_nutrition(["52771"])["recipes"][0]["ingredient_breakdown"]
    assert breakdown[0] == {
        "position": 1, "ingredient": "Tomato", "measure": "100 g", "grams": 100.0, "grams_basis": "measured",
        "usda_match": "Tomato, raw", "calories": 100.0, "protein": 10.0,
    }


async def test_cached_entry_without_portions_is_looked_up_again():
    service = service_with_cached_tomato()
    service.nutrition_repo.get_cached_bulk(["tomato"])["tomato"].portions = None
    await service.enrich_recipes(["52771"])
    assert service.usda.requested == [["tomato", "olive oil"]]


async def test_pieces_and_spoons_use_usda_portions():
    meal = {
        **sample_meal(),
        "strMeasure1": "2 finely chopped",
        "strMeasure2": "1 tbsp",
        "strIngredient3": "Salt",
        "strMeasure3": "To taste",
    }
    portions = {
        "tomato": [{"unit": "medium whole", "grams": 123.0}, {"unit": "cup, chopped", "grams": 180.0}],
        "olive oil": [{"unit": "tsp", "grams": 4.5}],
    }
    service = service_with_cached_tomato(meal, portions)
    await service.enrich_recipes(["52771"], refresh=True)
    recipe = service.get_nutrition(["52771"])["recipes"][0]
    by_name = {row["ingredient"]: row for row in recipe["ingredient_breakdown"]}
    assert by_name["Tomato"]["grams"] == 246.0
    assert by_name["Tomato"]["grams_basis"] == "USDA portion: 1 medium whole = 123 g"
    assert by_name["Olive Oil"]["grams"] == 13.5
    assert recipe["estimated_volume_conversions"] == []
    assert recipe["uncovered_ingredients"] == [
        {"ingredient": "Salt", "measure": "To taste", "reason": "amount_not_convertible"}
    ]
