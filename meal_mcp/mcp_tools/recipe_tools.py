from db.db import session_scope
from mcp_tools.server import mcp
from services.recipe_service import RecipeService


@mcp.tool()
async def search_recipes(queries: list[str]) -> dict:
    """Search TheMealDB for several recipe queries in one tool call."""
    with session_scope() as session:
        return await RecipeService(session).search_recipes(queries)


@mcp.tool()
async def save_recipes(mealdb_ids: list[str]) -> dict:
    """Load and save several TheMealDB recipes, including ingredients."""
    with session_scope() as session:
        return await RecipeService(session).save_recipes(mealdb_ids)


@mcp.tool()
def list_recipes() -> list[dict]:
    """List all locally saved recipes and variants (is_variant, parent_mealdb_id, variant_ids)."""
    with session_scope() as session:
        return RecipeService(session).list_recipes()


@mcp.tool()
def get_recipes(mealdb_ids: list[str]) -> dict:
    """Return several saved recipes or variants in full: ingredients, instructions and, for variants,
    the original recipe, constraints and changes."""
    with session_scope() as session:
        return RecipeService(session).get_recipes(mealdb_ids)


@mcp.tool()
def delete_recipes(mealdb_ids: list[str]) -> dict:
    """Delete several locally saved recipes or variants. Deleting an original also deletes its variants."""
    with session_scope() as session:
        return RecipeService(session).delete_recipes(mealdb_ids)
