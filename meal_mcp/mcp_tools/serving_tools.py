from db.db import session_scope
from mcp_tools.server import READ_ONLY, mcp
from services.serving_service import ServingService


@mcp.tool()
def set_recipe_servings(recipes: list[dict]) -> dict:
    """Store how many servings recipes make: [{mealdb_id, servings}]; variants inherit it. Use what
    the user or the instructions say, do not guess."""
    with session_scope() as session:
        return ServingService(session).set_servings(recipes)


@mcp.tool(annotations=READ_ONLY)
def scale_recipes(recipes: list[dict]) -> dict:
    """Show amounts for another number of servings: [{mealdb_id, servings}]. Needs known servings;
    nothing is saved (save_adapted_recipes keeps it as a variant)."""
    with session_scope() as session:
        return ServingService(session).scale(recipes)
