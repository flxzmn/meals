from db.db import session_scope
from mcp_tools.server import mcp
from services.nutrition_service import NutritionService


@mcp.tool()
async def enrich_recipes(mealdb_ids: list[str], refresh: bool = False) -> dict:
    """Enrich several saved recipes with cached USDA nutrition data in one tool call.

    Set refresh=true to look up all ingredients again and replace cached USDA matches.
    """
    with session_scope() as session:
        return await NutritionService(session).enrich_recipes(mealdb_ids, refresh)


@mcp.tool()
def get_nutrition(mealdb_ids: list[str]) -> dict:
    """Return estimated nutrition summaries for several saved recipes.

    Call enrich_recipes first: ingredients without USDA data are not counted.
    ingredient_breakdown lists the USDA food used for each ingredient and how its grams were derived
    (grams_basis: measured, USDA portion weight for pieces and spoons, or approx. 1 g/ml for volumes).
    """
    with session_scope() as session:
        return NutritionService(session).get_nutrition(mealdb_ids)


@mcp.tool()
async def calculate_nutrition(ingredients: list[dict]) -> dict:
    """Calculate nutrition of free ingredients without a saved recipe: [{name, measure}], e.g.
    [{"name": "Hähnchen", "measure": "500 g"}, {"name": "Zwiebeln", "measure": "2"}].

    Uses the same USDA matching, portion weights and manual rules as recipes. German names work.
    """
    with session_scope() as session:
        return await NutritionService(session).calculate(ingredients)


@mcp.tool()
async def compare_nutrition(mealdb_ids: list[str], enrich: bool = True) -> dict:
    """Compare the nutrition of recipe variants with their originals.

    Pass variant IDs, or an original ID to compare all its variants. Returns calories, protein,
    fat and carbs of both, the absolute and percent difference, the coverage (how many ingredients
    are counted) and the effect of each ingredient change. enrich=true loads missing USDA data first.
    If a replaced ingredient has no data, comparable is false and difference is null: do not present
    partial_difference as a result; store values with set_ingredient_matches and compare again.
    """
    with session_scope() as session:
        return await NutritionService(session).compare_variants(mealdb_ids, enrich)
