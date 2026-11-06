from db.db import session_scope
from mcp_tools.server import READ_ONLY, mcp
from services.nutrition_service import NutritionService


@mcp.tool()
async def enrich_recipes(mealdb_ids: list[str], refresh: bool = False) -> dict:
    """Load USDA nutrition data for saved recipes. If complete is false, call again with the same IDs.
    refresh=true looks up all ingredients again (use with a few recipes)."""
    with session_scope() as session:
        return await NutritionService(session).enrich_recipes(mealdb_ids, refresh)


@mcp.tool(annotations=READ_ONLY)
def get_nutrition(mealdb_ids: list[str], compact: bool | None = None) -> dict:
    """Estimated nutrition of saved recipes (enrich_recipes first; ingredients without data are not counted).

    ingredient_breakdown gives the USDA food and grams_basis per ingredient; per_serving appears once
    servings are known. Above 5 recipes compact (totals, coverage, uncovered); compact=false forces detail.
    """
    with session_scope() as session:
        return NutritionService(session).get_nutrition(mealdb_ids, compact)


@mcp.tool(annotations=READ_ONLY)
async def calculate_nutrition(ingredients: list[dict], servings: int | None = None) -> dict:
    """Nutrition of free ingredients without a saved recipe: [{name, measure}], e.g.
    [{"name": "Hähnchen", "measure": "500 g"}]. Same matching as recipes; English names match more
    reliably. Check usda_match and fix it with set_ingredient_matches."""
    with session_scope() as session:
        return await NutritionService(session).calculate(ingredients, servings)


@mcp.tool()
async def compare_nutrition(mealdb_ids: list[str], enrich: bool = True, compact: bool | None = None) -> dict:
    """Compare variants with their originals (variant IDs, or an original ID for all its variants):
    nutrients, difference, coverage and the effect of each change.

    If comparable is false, difference is null: do not present partial_difference as a result; notes
    names the cause. Above 5 comparisons compact; compact=false forces detail.
    """
    with session_scope() as session:
        return await NutritionService(session).compare_variants(mealdb_ids, enrich, compact)
