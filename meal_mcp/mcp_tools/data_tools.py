from db.db import session_scope
from mcp_tools.server import mcp
from services.data_service import DataService


@mcp.tool()
def export_data(path: str | None = None) -> dict:
    """Save all data (recipes, variants, rules, decisions, matches) to a JSON file; default folder:
    exports in the data folder. Existing files are not overwritten."""
    with session_scope() as session:
        return DataService(session).export_data(path)


@mcp.tool()
def import_data(path: str) -> dict:
    """Load a file from export_data. Only adds what is missing; a damaged file imports nothing."""
    with session_scope() as session:
        return DataService(session).import_data(path)
