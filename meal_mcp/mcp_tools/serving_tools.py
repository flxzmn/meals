from db.db import session_scope
from mcp_tools.server import mcp
from services.serving_service import ServingService


@mcp.tool()
def set_recipe_servings(recipes: list[dict]) -> dict:
    """Store how many servings recipes make: [{mealdb_id, servings}]. Variants inherit the value of
    their original unless they have their own.

    TheMealDB has no servings: use what the user says or what the instructions state, do not guess.
    get_nutrition and compare_nutrition then also return per_serving.
    """
    with session_scope() as session:
        return ServingService(session).set_servings(recipes)


@mcp.tool()
def scale_recipes(recipes: list[dict]) -> dict:
    """Show ingredient amounts for another number of servings: [{mealdb_id, servings}].

    Needs known servings (set_recipe_servings). Nothing is saved; save_adapted_recipes stores a
    scaled recipe as a variant if the user wants to keep it.
    """
    with session_scope() as session:
        return ServingService(session).scale(recipes)
