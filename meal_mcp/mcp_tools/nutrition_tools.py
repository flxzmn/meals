from db.db import session_scope
from mcp_tools.server import mcp
from services.nutrition_service import NutritionService


@mcp.tool()
async def enrich_recipes(mealdb_ids: list[str], refresh: bool = False) -> dict:
    """Enrich several saved recipes with cached USDA nutrition data in one tool call.

    Set refresh=true to look up all ingredients again and replace cached USDA matches; use it with a few
    recipes at a time. Long runs stop in time and save their progress: if complete is false, call again
    with the same IDs.
    """
    with session_scope() as session:
        return await NutritionService(session).enrich_recipes(mealdb_ids, refresh)


@mcp.tool()
def get_nutrition(mealdb_ids: list[str], compact: bool | None = None) -> dict:
    """Return estimated nutrition summaries for several saved recipes.

    Call enrich_recipes first: ingredients without USDA data are not counted.
    ingredient_breakdown lists the USDA food used for each ingredient and how its grams were derived
    (grams_basis: measured, USDA portion weight for pieces and spoons, or approx. 1 g/ml for volumes).
    per_serving is null until the servings are known (set_recipe_servings).
    Above 5 recipes the result is compact (totals, coverage, uncovered ingredients); compact=false forces
    full detail, compact=true forces the short form.
    """
    with session_scope() as session:
        return NutritionService(session).get_nutrition(mealdb_ids, compact)


@mcp.tool()
async def calculate_nutrition(ingredients: list[dict], servings: int | None = None) -> dict:
    """Calculate nutrition of free ingredients without a saved recipe: [{name, measure}], e.g.
    [{"name": "Hähnchen", "measure": "500 g"}, {"name": "Zwiebeln", "measure": "2"}].

    Uses the same USDA matching, portion weights and manual rules as recipes. Common German names
    are translated; English names match more reliably. Check usda_match in ingredient_breakdown and
    fix wrong matches with set_ingredient_matches. With servings the result also contains per_serving.
    """
    with session_scope() as session:
        return await NutritionService(session).calculate(ingredients, servings)


@mcp.tool()
async def compare_nutrition(mealdb_ids: list[str], enrich: bool = True, compact: bool | None = None) -> dict:
    """Compare the nutrition of recipe variants with their originals.

    Pass variant IDs, or an original ID to compare all its variants. Returns calories, protein,
    fat and carbs of both, the absolute and percent difference, the coverage (how many ingredients
    are counted) and the effect of each ingredient change. enrich=true loads missing USDA data first.
    If a replaced ingredient has no data, comparable is false and difference is null: do not present
    partial_difference as a result; notes names the cause. Above 5 comparisons the result is compact
    (only uncounted change_effects, no uncovered_ingredients); compact=false forces full detail.
    """
    with session_scope() as session:
        return await NutritionService(session).compare_variants(mealdb_ids, enrich, compact)
