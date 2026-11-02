from db.db import session_scope
from mcp_tools.server import mcp
from services.substitution_service import SubstitutionService


@mcp.tool()
def add_substitutions(substitutions: list[dict]) -> dict:
    """Add several ingredient substitutions to the local knowledge base, or change their quantity rule.

    Optional per item: quantity_ratio (grams of target per gram of source, default 1.0) and
    quantity_note (e.g. "1 egg = 1 tbsp ground flaxseed + 3 tbsp water"). For an existing pair they
    replace the stored rule (listed in updated); adapt_recipes uses the ratio for substitute amounts.
    """
    with session_scope() as session:
        return SubstitutionService(session).add_substitutions(substitutions)


@mcp.tool()
def find_substitutions(ingredients: list[str], constraints: dict | None = None) -> dict:
    """Find suitable substitutions for several ingredients in one call."""
    with session_scope() as session:
        return SubstitutionService(session).find_substitutions(ingredients, constraints)


@mcp.tool()
def list_substitutions() -> list[dict]:
    """List all substitutions in the local knowledge base."""
    with session_scope() as session:
        return SubstitutionService(session).list_substitutions()


@mcp.tool()
def delete_substitutions(substitutions: list[dict]) -> dict:
    """Delete several substitutions identified by source and target ingredient."""
    with session_scope() as session:
        return SubstitutionService(session).delete_substitutions(substitutions)


@mcp.tool()
def adapt_recipes(mealdb_ids: list[str], constraints: dict | None = None, compact: bool | None = None) -> dict:
    """Adapt several saved recipes using the substitution knowledge base.

    Substitute amounts follow the quantity_ratio of each substitution: mass and volume are scaled,
    piece counts are converted to grams with USDA portion weights (run enrich_recipes first).
    Amounts that cannot be converted are listed in unverified_quantities.
    hidden_ingredients lists known ingredients that stand only in a measure text or the instructions and
    were not replaced: tell the user. Above 5 recipes the result is compact (no instructions, short
    ingredient rows); save_adapted_recipes accepts it. compact=false forces full detail.
    The result is not stored. To keep a variant, pass items of adapted_recipes to save_adapted_recipes.
    """
    with session_scope() as session:
        return SubstitutionService(session).adapt_recipes(mealdb_ids, constraints, compact)
