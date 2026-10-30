from db.db import session_scope
from mcp_tools.server import mcp
from services.instruction_service import InstructionService


@mcp.tool()
def rewrite_instructions(mealdb_ids: list[str], force: bool = False) -> dict:
    """Prepare rewriting the instructions of several saved recipe variants.

    Returns one request per variant with the current instructions, the ingredient changes, the
    replaced terms and guidelines. Write the new instructions yourself following the guidelines,
    then call save_rewritten_instructions. Variants already rewritten are skipped unless force=true.
    """
    with session_scope() as session:
        return InstructionService(session).rewrite_requests(mealdb_ids, force)


@mcp.tool()
def save_rewritten_instructions(rewrites: list[dict]) -> dict:
    """Store rewritten instructions for several variants: [{mealdb_id, instructions}].

    The text is marked as LLM-generated (instructions_source='llm'). Warnings list replaced
    ingredients that are still mentioned. Original recipes cannot be changed.
    """
    with session_scope() as session:
        return InstructionService(session).save_rewrites(rewrites)
