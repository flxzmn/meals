"""v1.1: data folder, export and import, servings, tool call log and evals."""

import json
import sqlite3
from pathlib import Path

import pytest
from fastmcp import Client
from sqlalchemy import create_engine, select

import main  # noqa: F401  registers all MCP tools
from config.settings import Settings, default_data_dir
from db import db as db_module
from db.db import Base, adopt_legacy_database, session_scope
from db.models import IngredientMatchRule, NutritionCache, Recipe, Substitution
from mcp_tools.server import mcp
from repo.recipe_repo import RecipeRepo
from scripts.run_evals import load_cases, parse_calls, score_case
from services.data_service import DataService
from services.match_service import MatchService
from services.nutrition_service import NutritionService
from services.serving_service import ServingService, clean_servings
from services.variant_service import VariantService
from tests.test_compare import FakeUSDA
from tests.test_substitutions import build_session, seed_recipe
from tests.test_variants import adapted


def session_with_variant():
    session = build_session()
    VariantService(session).save_variants([adapted(session)])
    return session


# Data folder


def test_data_folder_is_per_user_and_outside_the_extension():
    home = Path("/home/x")
    assert default_data_dir("win32", {"APPDATA": "C:/Roaming"}, home) == Path("C:/Roaming/MealMCP")
    assert default_data_dir("win32", {}, home) == home / "AppData" / "Roaming" / "MealMCP"
    assert default_data_dir("darwin", {}, home) == home / "Library" / "Application Support" / "MealMCP"


def test_data_folder_setting_moves_the_database(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("MEAL_DATA_DIR", str(tmp_path))
    settings = Settings(_env_file=None)
    assert settings.database_url == f"sqlite:///{(tmp_path / 'recipe_mcp.db').as_posix()}"


def test_database_url_setting_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///C:/elsewhere.db")
    assert Settings(_env_file=None).database_url == "sqlite:///C:/elsewhere.db"


def test_old_database_is_copied_once(tmp_path):
    legacy, target = tmp_path / "old" / "a.db", tmp_path / "new" / "sub" / "a.db"
    legacy.parent.mkdir()
    legacy.write_bytes(b"old")
    assert adopt_legacy_database(legacy, target) is True
    assert target.read_bytes() == b"old"
    legacy.write_bytes(b"changed")
    assert adopt_legacy_database(legacy, target) is False
    assert target.read_bytes() == b"old"


def test_folder_is_created_without_old_database(tmp_path):
    target = tmp_path / "new" / "a.db"
    assert adopt_legacy_database(tmp_path / "missing.db", target) is False
    assert target.parent.is_dir()
    assert not target.exists()


def test_servings_column_is_added_to_old_database(tmp_path):
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE recipes (id INTEGER PRIMARY KEY, mealdb_id VARCHAR(50), name VARCHAR(255))")
    connection.commit()
    connection.close()
    engine = create_engine(f"sqlite:///{path}")
    db_module.add_missing_columns(engine)
    engine.dispose()
    connection = sqlite3.connect(path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(recipes)")}
    connection.close()
    assert "servings" in columns


def test_gram_estimates_of_an_old_database_are_recomputed(tmp_path):
    # Stored by the 1.0.0 parser; the measures come from the Weltküche run.
    stored = [("1 ½ tbsp", 7.5), ("2 x 400g", None), ("2-1/2 cups", 120.0), ("2 tbs", None), ("100 g", 100.0)]
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE ingredients (id INTEGER PRIMARY KEY, measure VARCHAR(100), estimated_grams FLOAT)")
    connection.executemany("INSERT INTO ingredients (measure, estimated_grams) VALUES (?, ?)", stored)
    connection.commit()
    connection.close()
    engine = create_engine(f"sqlite:///{path}")
    assert db_module.refresh_estimated_grams(engine) == 4
    assert db_module.refresh_estimated_grams(engine) == 0
    engine.dispose()
    connection = sqlite3.connect(path)
    grams = dict(connection.execute("SELECT measure, estimated_grams FROM ingredients"))
    connection.close()
    assert grams == {"1 ½ tbsp": 22.5, "2 x 400g": 800.0, "2-1/2 cups": 600.0, "2 tbs": 30.0, "100 g": 100.0}


# Export and import


async def filled_session():
    session = session_with_variant()
    ServingService(session).set_servings([{"mealdb_id": "test-1", "servings": 4}])
    await MatchService(session).set_matches([{"ingredient": "tempeh", "calories_per_100g": 190}])
    MatchService(session).rules.add_rejection("milk", "99", "wrong")
    session.add(Substitution(source_ingredient="beef", target_ingredient="seitan", tags=["vegan"]))
    session.flush()
    return session


async def test_export_and_import_restore_everything(tmp_path):
    session = await filled_session()
    path = tmp_path / "backup.json"
    exported = DataService(session).export_data(str(path))
    assert exported["status"] == "exported"
    assert exported["counts"]["recipes"] == 2

    fresh = build_session()
    result = DataService(fresh).import_data(str(path))
    assert result["status"] == "imported"
    assert result["imported"]["recipes"] == {"added": 2, "kept": 0}

    variant = fresh.scalar(select(Recipe).where(Recipe.mealdb_id == "test-1-v1"))
    original = variant.parent
    assert original.mealdb_id == "test-1"
    assert variant.effective_servings == 4
    assert [row.name for row in variant.ingredients] == [row.name for row in session.scalar(select(Recipe).where(Recipe.mealdb_id == "test-1-v1")).ingredients]
    assert variant.changes and variant.constraints
    assert fresh.scalar(select(NutritionCache).where(NutritionCache.normalized_name == "tempeh")).usda_fdc_id == "custom"
    assert fresh.scalar(select(IngredientMatchRule).where(IngredientMatchRule.normalized_name == "milk")).rejected_fdc_ids == ["99"]
    assert fresh.scalar(select(Substitution).where(Substitution.source_ingredient == "beef")).tags == ["vegan"]
    assert original.created_at is not None


async def test_second_import_changes_nothing_and_keeps_local_edits(tmp_path):
    session = await filled_session()
    path = tmp_path / "backup.json"
    DataService(session).export_data(str(path))
    ServingService(session).set_servings([{"mealdb_id": "test-1", "servings": 8}])

    result = DataService(session).import_data(str(path))
    assert result["imported"]["recipes"] == {"added": 0, "kept": 2}
    assert result["imported"]["substitutions"]["added"] == 0
    assert session.scalar(select(Recipe).where(Recipe.mealdb_id == "test-1")).servings == 8


async def test_export_does_not_overwrite_and_needs_json(tmp_path):
    session = await filled_session()
    path = tmp_path / "backup.json"
    path.write_text("keep", encoding="utf-8")
    assert DataService(session).export_data(str(path))["status"] == "error"
    assert path.read_text(encoding="utf-8") == "keep"
    assert DataService(session).export_data(str(tmp_path / "backup.txt"))["status"] == "error"


async def test_export_contains_no_api_key(tmp_path, monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "usda_api_key", "secret-test-key")
    path = tmp_path / "backup.json"
    DataService(await filled_session()).export_data(str(path))
    assert "secret-test-key" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("content", ["not json", "[]", '{"format": "other"}', '{"format": "meal-mcp-export", "version": 99}'])
def test_foreign_files_are_refused(tmp_path, content):
    path = tmp_path / "file.json"
    path.write_text(content, encoding="utf-8")
    assert DataService(build_session()).import_data(str(path))["status"] == "error"


def test_missing_file_is_an_error(tmp_path):
    assert DataService(build_session()).import_data(str(tmp_path / "none.json"))["status"] == "error"


def test_damaged_file_imports_nothing(tmp_path):
    session = build_session()
    path = tmp_path / "damaged.json"
    path.write_text(json.dumps({
        "format": "meal-mcp-export", "version": 1,
        "recipes": [{"mealdb_id": "1", "name": "Good", "ingredients": []}, {"name": "No ID"}],
    }), encoding="utf-8")
    result = DataService(session).import_data(str(path))
    assert result["status"] == "error"
    assert session.scalar(select(Recipe)) is None


def test_variant_without_original_is_reported(tmp_path):
    session = build_session()
    path = tmp_path / "file.json"
    path.write_text(json.dumps({
        "format": "meal-mcp-export", "version": 1,
        "recipes": [{"mealdb_id": "1-v1", "name": "Orphan", "parent_mealdb_id": "1", "ingredients": []}],
    }), encoding="utf-8")
    result = DataService(session).import_data(str(path))
    assert result["status"] == "partial_success"
    assert result["errors"][0]["mealdb_id"] == "1-v1"


# Servings


@pytest.mark.parametrize("value, expected", [(4, 4), ("4", 4), (4.0, 4), (0, None), (-1, None), (2.5, None), (True, None), ("x", None), (None, None), (float("inf"), None), (float("nan"), None)])
def test_clean_servings(value, expected):
    assert clean_servings(value) == expected


async def test_per_serving_appears_when_servings_are_known():
    session = session_with_variant()
    service = NutritionService(session)
    service.usda = FakeUSDA()
    await service.enrich_recipes(["test-1", "test-1-v1"])
    assert service.get_nutrition(["test-1"])["recipes"][0]["per_serving"] is None

    ServingService(session).set_servings([{"mealdb_id": "test-1", "servings": 2}])
    original = service.get_nutrition(["test-1"])["recipes"][0]
    assert original["calories"] == 260.0
    assert original["per_serving"]["calories"] == 130.0
    # The variant inherits the servings of its original.
    assert service.get_nutrition(["test-1-v1"])["recipes"][0]["per_serving"]["calories"] == 117.5


async def test_variant_can_have_its_own_servings():
    session = session_with_variant()
    service = ServingService(session)
    service.set_servings([{"mealdb_id": "test-1", "servings": 2}, {"mealdb_id": "test-1-v1", "servings": 5}])
    recipes = {row.mealdb_id: row.effective_servings for row in service.repo.get_bulk(["test-1", "test-1-v1"])}
    assert recipes == {"test-1": 2, "test-1-v1": 5}


async def test_compare_reports_per_serving():
    session = session_with_variant()
    ServingService(session).set_servings([{"mealdb_id": "test-1", "servings": 2}])
    service = NutritionService(session)
    service.usda = FakeUSDA()
    comparison = (await service.compare_variants(["test-1-v1"]))["comparisons"][0]
    assert comparison["original"]["per_serving"]["calories"] == 130.0
    assert comparison["variant"]["per_serving"]["calories"] == 117.5


async def test_calculate_with_servings():
    service = NutritionService(build_session())
    service.usda = FakeUSDA()
    ingredients = [{"name": "chicken", "measure": "200 g"}]
    assert (await service.calculate(ingredients, 2))["per_serving"]["calories"] == 200.0
    assert (await service.calculate(ingredients))["per_serving"] is None
    assert (await service.calculate(ingredients, 0))["status"] == "error"


def test_scaling_multiplies_amounts_and_saves_nothing():
    session = build_session()
    RecipeRepo(session).save_bulk([{
        "idMeal": "1", "strMeal": "Soup", "strIngredient1": "Chicken", "strMeasure1": "1.2 kg",
        "strIngredient2": "Salt", "strMeasure2": "To taste", "strIngredient3": "Onion", "strMeasure3": "2",
    }])
    service = ServingService(session)
    service.set_servings([{"mealdb_id": "1", "servings": 4}])
    result = service.scale([{"mealdb_id": "1", "servings": 6}])["recipes"][0]
    assert result["factor"] == 1.5
    assert [row["scaled_measure"] for row in result["ingredients"]] == ["1.8 kg", "To taste", "3"]
    assert result["unscaled_ingredients"] == ["Salt"]
    assert [row.measure for row in service.repo.get_bulk(["1"])[0].ingredients] == ["1.2 kg", "To taste", "2"]


def test_scaling_needs_known_servings():
    session = build_session()
    seed_recipe(session)
    service = ServingService(session)
    result = service.scale([{"mealdb_id": "test-1", "servings": 6}, {"mealdb_id": "none", "servings": 6}])
    assert result["recipes"] == []
    assert "set_recipe_servings" in result["errors"][0]["reason"]
    assert result["errors"][1]["reason"] == "Recipe not found."


def test_invalid_servings_are_refused():
    session = build_session()
    seed_recipe(session)
    result = ServingService(session).set_servings([{"mealdb_id": "test-1", "servings": 0}])
    assert result["status"] == "nothing_updated"
    assert RecipeRepo(session).get_bulk(["test-1"])[0].servings is None


# MCP layer and tool call log


@pytest.fixture
async def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'v11.db'}")
    Base.metadata.create_all(engine)
    original_bind = db_module.SessionLocal.kw["bind"]
    db_module.SessionLocal.configure(bind=engine)
    try:
        with session_scope() as session:
            seed_recipe(session)
        async with Client(mcp) as mcp_client:
            yield mcp_client
    finally:
        db_module.SessionLocal.configure(bind=original_bind)
        engine.dispose()


async def test_new_tools_work_through_mcp(client, tmp_path):
    names = {tool.name for tool in await client.list_tools()}
    assert {"export_data", "import_data", "set_recipe_servings", "scale_recipes"} <= names

    await client.call_tool("set_recipe_servings", {"recipes": [{"mealdb_id": "test-1", "servings": 2}]})
    scaled = await client.call_tool("scale_recipes", {"recipes": [{"mealdb_id": "test-1", "servings": 4}]})
    assert scaled.data["recipes"][0]["factor"] == 2.0

    path = tmp_path / "backup.json"
    assert (await client.call_tool("export_data", {"path": str(path)})).data["status"] == "exported"
    assert (await client.call_tool("import_data", {"path": str(path)})).data["imported"]["recipes"]["kept"] == 1


async def test_tool_calls_are_logged_without_arguments(client, capsys):
    await client.call_tool("list_recipes", {})
    await client.call_tool("get_recipes", {"mealdb_ids": ["private-value"]})
    calls = parse_calls(capsys.readouterr().err)
    assert calls == [{"tool": "list_recipes", "status": "ok"}, {"tool": "get_recipes", "status": "ok"}]


async def test_log_stays_out_of_stdout(client, capsys):
    await client.call_tool("list_recipes", {})
    assert "TOOL_CALL" not in capsys.readouterr().out


# Evals


def calls_of(*names):
    return [{"tool": name, "status": "ok"} for name in names]


def test_score_requires_order():
    case = {"id": "x", "required": ["a", "b"], "forbidden": []}
    assert score_case(case, calls_of("a", "other", "b"))["passed"]
    assert score_case(case, calls_of("b", "a"))["missing"] == ["b"]


def test_score_accepts_alternatives():
    case = {"id": "x", "required": [["a", "b"]], "forbidden": []}
    assert score_case(case, calls_of("b"))["passed"]
    assert not score_case(case, calls_of("c"))["passed"]


def test_score_rejects_forbidden_and_failed_tools():
    case = {"id": "x", "required": ["a"], "forbidden": ["z"]}
    assert score_case(case, calls_of("a", "z"))["forbidden_used"] == ["z"]
    result = score_case(case, [{"tool": "a", "status": "error"}])
    assert result["failed_calls"] == ["a"]
    assert not result["passed"]


def test_parse_calls_reads_only_marked_lines():
    text = "2026 [Meal MCP] [info] Message\nTOOL_CALL list_recipes ok\nnoise\nTOOL_CALL get_recipes error\r\n"
    assert [call["tool"] for call in parse_calls(text)] == ["list_recipes", "get_recipes"]


async def test_eval_cases_name_existing_tools():
    names = {tool.name for tool in await mcp.list_tools()}
    cases = load_cases()
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["prompt"] and case["checks"]
        used = list(case.get("forbidden", []))
        for step in case["required"]:
            used.extend([step] if isinstance(step, str) else step)
        assert set(used) <= names, case["id"]
