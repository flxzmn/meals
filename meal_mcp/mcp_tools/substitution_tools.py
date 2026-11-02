from db.db import session_scope
from mcp_tools.server import mcp
from services.substitution_service import SubstitutionService


@mcp.tool()
def add_substitutions(substitutions: list[dict]) -> dict:
    """Add ingredient substitutions to the knowledge base, or change the quantity rule of an existing pair
    (listed in updated). Optional: quantity_ratio (grams of target per gram of source, default 1.0) and
    quantity_note (e.g. "1 egg = 1 tbsp ground flaxseed + 3 tbsp water")."""
    with session_scope() as session:
        return SubstitutionService(session).add_substitutions(substitutions)


@mcp.tool()
def find_substitutions(ingredients: list[str] | None = None, constraints: dict | None = None) -> dict:
    """Substitution rules per source ingredient, optionally filtered by constraints. Without ingredients,
    all rules in the knowledge base."""
    with session_scope() as session:
        return SubstitutionService(session).find_substitutions(ingredients, constraints)


@mcp.tool()
def delete_substitutions(substitutions: list[dict]) -> dict:
    """Delete substitutions: [{source_ingredient, target_ingredient}]."""
    with session_scope() as session:
        return SubstitutionService(session).delete_substitutions(substitutions)


@mcp.tool()
def adapt_recipes(mealdb_ids: list[str], constraints: dict | None = None, compact: bool | None = None) -> dict:
    """Adapt saved recipes with the substitution rules. Nothing is stored: pass items of adapted_recipes
    to save_adapted_recipes to keep them.

    Substitute amounts follow quantity_ratio; pieces become grams via USDA portions (enrich_recipes
    first), the rest is listed in unverified_quantities. Tell the user about hidden_ingredients (only in
    a measure text or the instructions, not replaced). Above 5 recipes compact; compact=false forces detail.
    """
    with session_scope() as session:
        return SubstitutionService(session).adapt_recipes(mealdb_ids, constraints, compact)
