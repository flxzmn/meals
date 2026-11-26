from db.db import session_scope
from mcp_tools.server import READ_ONLY, mcp
from services.match_service import MatchService


@mcp.tool(annotations=READ_ONLY)
async def search_usda_foods(queries: list[str]) -> dict:
    """Search USDA foods for several terms: fdc_id, description and nutrients per 100 g, to pick a
    match for set_ingredient_matches."""
    with session_scope() as session:
        return await MatchService(session).search_foods(queries)


@mcp.tool()
async def set_ingredient_matches(matches: list[dict]) -> dict:
    """Pin nutrition data to ingredients, kept on refresh: {ingredient, fdc_id, note}, or label values
    {ingredient, calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, note}."""
    with session_scope() as session:
        return await MatchService(session).set_matches(matches)


@mcp.tool()
async def reject_ingredient_matches(rejections: list[dict]) -> dict:
    """Reject wrong USDA matches: [{ingredient, fdc_id (default: current), note}]. The next best match
    is loaded (new_matches)."""
    with session_scope() as session:
        return await MatchService(session).reject_matches(rejections)


@mcp.tool(annotations=READ_ONLY)
def list_ingredient_matches(ingredients: list[str] | None = None) -> list[dict]:
    """USDA matches of ingredients with source (auto or manual), rejected foods and notes; without
    ingredients all of them."""
    with session_scope() as session:
        return MatchService(session).list_matches(ingredients)
