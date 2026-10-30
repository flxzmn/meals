"""Sprint 10 acceptance test over the MCP layer: USDA matches can be inspected, corrected and rejected.

Runs the real FastMCP tools through an in-memory MCP client against a temporary SQLite database.
USDA is replaced by a fake HTTP transport with two fenugreek foods (see tests/test_matches.py).
"""

import httpx
import pytest
from fastmcp import Client
from sqlalchemy import create_engine

import main  # noqa: F401  registers all MCP tools
from config.settings import settings
from db import db as db_module
from db.db import Base, session_scope
from mcp_tools.server import mcp
from repo.recipe_repo import RecipeRepo
from services import match_service, nutrition_service
from services.usda_service import USDAService
from tests.test_matches import handler


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "usda_api_key", "test-key")

    def fake_usda():
        return USDAService(httpx.MockTransport(handler), retry_delay=0)

    monkeypatch.setattr(match_service, "USDAService", fake_usda)
    monkeypatch.setattr(nutrition_service, "USDAService", fake_usda)
    engine = create_engine(f"sqlite:///{tmp_path / 'acceptance.db'}")
    Base.metadata.create_all(engine)
    original_bind = db_module.SessionLocal.kw["bind"]
    db_module.SessionLocal.configure(bind=engine)
    try:
        with session_scope() as session:
            RecipeRepo(session).save_bulk([{
                "idMeal": "1", "strMeal": "Curry", "strIngredient1": "Fenugreek", "strMeasure1": "3 tsp Dried",
            }])
        async with Client(mcp) as mcp_client:
            yield mcp_client
    finally:
        db_module.SessionLocal.configure(bind=original_bind)
        engine.dispose()


async def call(client, tool: str, **arguments):
    return (await client.call_tool(tool, arguments)).data


async def test_tool_list_contains_matching_tools(client):
    names = {tool.name for tool in await client.list_tools()}
    assert {"search_usda_foods", "set_ingredient_matches", "reject_ingredient_matches", "list_ingredient_matches"} <= names


async def test_01_match_is_visible(client):
    await call(client, "enrich_recipes", mealdb_ids=["1"])
    match = (await call(client, "list_ingredient_matches", ingredients=["fenugreek"]))[0]
    assert match["usda_match"] == "Spices, fenugreek seed"
    assert match["source"] == "auto"


async def test_02_wrong_match_is_rejected_and_replaced(client):
    await call(client, "enrich_recipes", mealdb_ids=["1"])
    result = await call(client, "reject_ingredient_matches", rejections=[{"ingredient": "fenugreek"}])
    assert result["new_matches"][0]["usda_match"] == "Fenugreek leaves, dried"
    await call(client, "enrich_recipes", mealdb_ids=["1"], refresh=True)
    match = (await call(client, "list_ingredient_matches", ingredients=["fenugreek"]))[0]
    assert match["fdc_id"] == "2"
    assert match["rejected_fdc_ids"] == ["1"]


async def test_03_match_is_corrected_by_hand(client):
    candidates = await call(client, "search_usda_foods", queries=["fenugreek"])
    leaves = next(row for row in candidates["results"]["fenugreek"] if "leaves" in row["description"])
    await call(client, "set_ingredient_matches", matches=[{"ingredient": "fenugreek", "fdc_id": leaves["fdc_id"]}])
    await call(client, "enrich_recipes", mealdb_ids=["1"], refresh=True)
    nutrition = (await call(client, "get_nutrition", mealdb_ids=["1"]))["recipes"][0]
    row = nutrition["ingredient_breakdown"][0]
    assert row["usda_match"] == "Fenugreek leaves, dried"
    assert row["grams"] == 11.1  # 3 tsp x 3.7 g USDA portion
