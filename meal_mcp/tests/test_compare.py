from services.match_service import MatchService
from services.nutrition_service import NutritionService
from services.variant_service import VariantService
from tests.test_substitutions import build_session, seed_recipe
from tests.test_variants import adapted

# kcal and protein per 100 g. Recipe test-1: 100 g chicken, 100 ml milk -> tempeh, oat milk.
VALUES = {
    "chicken": (200.0, 20.0),
    "milk": (60.0, 3.0),
    "tempeh": (190.0, 19.0),
    "oat milk": (45.0, 1.0),
}


class FakeUSDA:
    def __init__(self, missing=()):
        self.missing = set(missing)

    async def get_nutrients_bulk(self, ingredients):
        matched, missing = [], []
        for item in ingredients:
            name = item["normalized_name"]
            if name in self.missing or name not in VALUES:
                missing.append(item["source_name"])
                continue
            calories, protein = VALUES[name]
            matched.append({
                "normalized_name": name, "source_name": item["source_name"], "usda_fdc_id": "1",
                "matched_name": name, "calories_per_100g": calories, "protein_per_100g": protein,
                "fat_per_100g": 0.0, "carbs_per_100g": 0.0, "portions": [],
            })
        return {"matched": matched, "missing": missing, "errors": {}}


def service_with_variant(missing=()):
    session = build_session()
    VariantService(session).save_variants([adapted(session)])
    service = NutritionService(session)
    service.usda = FakeUSDA(missing)
    return service


async def test_variant_is_compared_with_original():
    result = await service_with_variant().compare_variants(["test-1-v1"])
    assert result["status"] == "success"
    comparison = result["comparisons"][0]
    assert comparison["original"]["calories"] == 260.0
    assert comparison["variant"]["calories"] == 235.0
    assert comparison["difference"]["calories"] == {"absolute": -25.0, "percent": -9.6}
    assert comparison["difference"]["protein"] == {"absolute": -3.0, "percent": -13.0}
    assert comparison["coverage"]["variant"] == {"covered": 2, "total": 2, "percent": 100.0}
    assert comparison["notes"] == []


async def test_change_effects_per_ingredient():
    result = await service_with_variant().compare_variants(["test-1-v1"])
    effects = result["comparisons"][0]["change_effects"]
    assert [(row["source"], row["target"], row["calories_before"], row["calories_after"]) for row in effects] == [
        ("Chicken", "tempeh", 200.0, 190.0),
        ("Milk", "oat milk", 60.0, 45.0),
    ]
    assert all(row["counted"] for row in effects)


async def test_original_id_compares_all_variants():
    service = service_with_variant()
    result = await service.compare_variants(["test-1"])
    assert [row["variant"]["mealdb_id"] for row in result["comparisons"]] == ["test-1-v1"]


async def test_missing_data_lowers_coverage_and_is_noted():
    result = await service_with_variant(missing={"tempeh"}).compare_variants(["test-1-v1"])
    comparison = result["comparisons"][0]
    assert comparison["coverage"]["variant"]["percent"] == 50.0
    assert comparison["notes"]
    assert comparison["change_effects"][0]["counted"] is False
    assert comparison["uncovered_ingredients"]["variant"][0]["ingredient"] == "tempeh"


async def test_original_without_variants_is_an_error():
    session = build_session()
    seed_recipe(session)
    service = NutritionService(session)
    service.usda = FakeUSDA()
    result = await service.compare_variants(["test-1", "missing"])
    assert result["status"] == "error"
    assert result["errors"][0]["mealdb_id"] == "test-1"
    assert result["missing_recipes"] == ["missing"]


async def test_uncounted_substitute_makes_comparison_not_comparable():
    comparison = (await service_with_variant(missing={"tempeh"}).compare_variants(["test-1-v1"]))["comparisons"][0]
    assert comparison["comparable"] is False
    assert comparison["difference"] is None
    assert comparison["partial_difference"]["calories"]["absolute"] == -215.0
    assert "tempeh" in comparison["notes"][0]


async def test_complete_comparison_is_comparable():
    comparison = (await service_with_variant().compare_variants(["test-1-v1"]))["comparisons"][0]
    assert comparison["comparable"] is True
    assert comparison["partial_difference"] is None


async def test_label_values_make_comparison_comparable():
    session = build_session()
    VariantService(session).save_variants([adapted(session)])
    service = NutritionService(session)
    service.usda = FakeUSDA(missing={"tempeh"})

    before = (await service.compare_variants(["test-1-v1"]))["comparisons"][0]
    assert before["comparable"] is False
    assert before["difference"] is None

    result = await MatchService(session).set_matches([{
        "ingredient": "tempeh", "calories_per_100g": 190, "protein_per_100g": 19, "fat_per_100g": 0, "carbs_per_100g": 0,
    }])
    assert result["status"] == "updated"

    after = (await service.compare_variants(["test-1-v1"]))["comparisons"][0]
    assert after["comparable"] is True
    assert after["partial_difference"] is None
    assert after["difference"]["calories"] == {"absolute": -25.0, "percent": -9.6}
    assert after["coverage"]["variant"]["percent"] == 100.0
    assert after["change_effects"][0]["counted"] is True
    assert after["notes"] == []
