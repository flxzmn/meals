from db.db import session_scope
from mcp_tools.server import mcp
from services.variant_service import VariantService


@mcp.tool()
def save_adapted_recipes(variants: list[dict]) -> dict:
    """Save adapted recipes as variants ("52795-v1"); originals stay unchanged. Pass items of
    adapted_recipes, optionally edited: source_mealdb_id and ingredients [{position, name, measure}]
    are required. Saving the same variant twice returns the existing one."""
    with session_scope() as session:
        return VariantService(session).save_variants(variants)


@mcp.tool()
def update_recipe_variants(updates: list[dict]) -> dict:
    """Edit saved variants (not originals): mealdb_id plus name, instructions, constraints or the
    complete new ingredients list [{position, name, measure}]."""
    with session_scope() as session:
        return VariantService(session).update_variants(updates)
