from db.db import session_scope
from mcp_tools.server import mcp
from services.data_service import DataService


@mcp.tool()
def export_data(path: str | None = None) -> dict:
    """Save all recipes, variants, substitutions, decisions, USDA matches and label values to a JSON file.

    Without path the file goes to the exports folder in the data folder; the result names the location.
    An existing file is not overwritten. The file holds no API key.
    """
    with session_scope() as session:
        return DataService(session).export_data(path)


@mcp.tool()
def import_data(path: str) -> dict:
    """Load a file written by export_data into the database.

    Adds what is missing and keeps everything that already exists, so nothing is overwritten and
    importing twice changes nothing. If the file is damaged, nothing is imported.
    """
    with session_scope() as session:
        return DataService(session).import_data(path)
