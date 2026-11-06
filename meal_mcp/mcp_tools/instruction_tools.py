from db.db import session_scope
from mcp_tools.server import READ_ONLY, mcp
from services.instruction_service import InstructionService


@mcp.tool(annotations=READ_ONLY)
def rewrite_instructions(mealdb_ids: list[str], force: bool = False) -> dict:
    """Prepare rewriting variant instructions: one request per variant with instructions, changes and
    guidelines. Write the text yourself, then call save_rewritten_instructions. force=true redoes
    rewritten ones."""
    with session_scope() as session:
        return InstructionService(session).rewrite_requests(mealdb_ids, force)


@mcp.tool()
def save_rewritten_instructions(rewrites: list[dict]) -> dict:
    """Store rewritten variant instructions: [{mealdb_id, instructions}], marked as LLM text. warnings
    list replaced ingredients still mentioned."""
    with session_scope() as session:
        return InstructionService(session).save_rewrites(rewrites)
