from db.db import session_scope
from mcp_tools.server import mcp
from services.image_service import ImageService
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
    """List all locally saved recipes and variants (is_variant, parent_mealdb_id, variant_ids;
    variants also constraints and change_count). Use get_recipes for details."""
    with session_scope() as session:
        return RecipeService(session).list_recipes()


@mcp.tool()
def get_recipes(mealdb_ids: list[str]) -> dict:
    """Return several saved recipes or variants in full: ingredients, instructions and, for variants,
    the original recipe, constraints and changes."""
    with session_scope() as session:
        return RecipeService(session).get_recipes(mealdb_ids)


@mcp.tool()
async def download_recipe_images(mealdb_ids: list[str], size: str = "medium", folder: str | None = None) -> dict:
    """Save the photos of several saved recipes or variants as JPEG files, e.g. for a recipe book.

    size: small (150 px, about 10 KB), medium (350 px, about 35 KB), large (500 px) or original
    (about 700 px). Without folder the files go
    to the images folder in the data folder; the result lists one path per recipe. Variants get the
    photo of their original. Files already there are not downloaded again.
    """
    with session_scope() as session:
        return await ImageService(session).download(mealdb_ids, size, folder)


@mcp.tool()
def delete_recipes(mealdb_ids: list[str]) -> dict:
    """Delete several locally saved recipes or variants. Deleting an original also deletes its variants."""
    with session_scope() as session:
        return RecipeService(session).delete_recipes(mealdb_ids)
