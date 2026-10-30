from db.db import session_scope
from mcp_tools.server import mcp
from services.match_service import MatchService


@mcp.tool()
async def search_usda_foods(queries: list[str]) -> dict:
    """Search USDA FoodData Central for several terms and list candidates with fdc_id, description,
    kcal, protein, fat and carbs per 100 g. Use it to choose a match by hand with set_ingredient_matches."""
    with session_scope() as session:
        return await MatchService(session).search_foods(queries)


@mcp.tool()
async def set_ingredient_matches(matches: list[dict]) -> dict:
    """Pin nutrition data to several ingredients and keep it, also with enrich_recipes refresh=true.

    Either a USDA food: {ingredient, fdc_id, note}. Or, for foods USDA does not have, values per
    100 g from a label: {ingredient, calories_per_100g, protein_per_100g, fat_per_100g,
    carbs_per_100g, note}. Stored values count in get_nutrition and compare_nutrition.
    """
    with session_scope() as session:
        return await MatchService(session).set_matches(matches)


@mcp.tool()
async def reject_ingredient_matches(rejections: list[dict]) -> dict:
    """Reject wrong USDA matches: [{ingredient, fdc_id (default: current match), note}].

    The rejected food is never chosen again for that ingredient; the next best match is loaded
    and returned in new_matches.
    """
    with session_scope() as session:
        return await MatchService(session).reject_matches(rejections)


@mcp.tool()
def list_ingredient_matches(ingredients: list[str] | None = None) -> list[dict]:
    """List USDA matches of ingredients with their source (auto or manual), rejected foods and notes.

    Without ingredients, lists all cached matches and rules.
    """
    with session_scope() as session:
        return MatchService(session).list_matches(ingredients)
