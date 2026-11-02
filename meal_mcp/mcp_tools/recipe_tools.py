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
    """List all saved recipes and variants. Variants have parent_mealdb_id, constraints and change_count;
    originals list their variant_ids. Empty fields are left out."""
    with session_scope() as session:
        return RecipeService(session).list_recipes()


@mcp.tool()
def get_recipes(mealdb_ids: list[str], compact: bool | None = None) -> dict:
    """Return saved recipes or variants with ingredients, instructions and, for variants, constraints and
    changes. Above 5 recipes compact (no instructions, image or changes); compact=false forces detail."""
    with session_scope() as session:
        return RecipeService(session).get_recipes(mealdb_ids, compact)


@mcp.tool()
async def download_recipe_images(mealdb_ids: list[str], size: str = "medium", folder: str | None = None) -> dict:
    """Save recipe photos as JPEG files, e.g. for a recipe book. size: small (150 px), medium (350 px),
    large (500 px) or original (about 700 px). Default folder: images in the data folder. Variants get
    their original's photo."""
    with session_scope() as session:
        return await ImageService(session).download(mealdb_ids, size, folder)


@mcp.tool()
def delete_recipes(mealdb_ids: list[str]) -> dict:
    """Delete several locally saved recipes or variants. Deleting an original also deletes its variants."""
    with session_scope() as session:
        return RecipeService(session).delete_recipes(mealdb_ids)
