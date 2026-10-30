from db.db import session_scope
from mcp_tools.server import mcp
from services.variant_service import VariantService


@mcp.tool()
def save_adapted_recipes(variants: list[dict]) -> dict:
    """Save several adapted recipes as variants with their own IDs. The originals stay unchanged.

    Pass the items of adapted_recipes from adapt_recipes, optionally edited. Each item needs
    source_mealdb_id and ingredients ([{position, name, measure}]); name, instructions, constraints
    and changes are optional. The server computes the differences to the original. Saving the same
    variant twice returns the existing one. Variant IDs look like "52795-v1" and work with
    get_recipes, enrich_recipes, get_nutrition and delete_recipes.
    """
    with session_scope() as session:
        return VariantService(session).save_variants(variants)


@mcp.tool()
def list_recipe_variants(source_mealdb_ids: list[str] | None = None) -> list[dict]:
    """List saved recipe variants, optionally only those of the given original recipes."""
    with session_scope() as session:
        return VariantService(session).list_variants(source_mealdb_ids)


@mcp.tool()
def update_recipe_variants(updates: list[dict]) -> dict:
    """Edit several saved variants. Original recipes cannot be edited.

    Each item needs mealdb_id and may set name, instructions, constraints and ingredients
    (the complete new list [{position, name, measure}]). Changes to the original are recomputed.
    """
    with session_scope() as session:
        return VariantService(session).update_variants(updates)
