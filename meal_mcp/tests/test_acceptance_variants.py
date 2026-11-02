"""Sprint 6 to 9 acceptance tests over the MCP layer: variants, instructions, amounts, comparison.

Flow from the handover protocol: adapt_recipes -> create variant -> save variant -> show and
edit it later. Runs the real FastMCP tools through an in-memory MCP client against a temporary
SQLite database, without network access (recipes are seeded, USDA is replaced).
"""

import pytest
from fastmcp import Client
from sqlalchemy import create_engine

import main  # noqa: F401  registers all MCP tools
from db import db as db_module
from db.db import Base, session_scope
from mcp_tools.server import mcp
from repo.recipe_repo import RecipeRepo
from services.usda_service import USDAService

CONSTRAINTS = {"diet": "vegan", "dislikes": ["tofu"]}

MEALS = [
    {
        "idMeal": "100", "strMeal": "Chicken Curry", "strCategory": "Chicken", "strArea": "Indian",
        "strInstructions": "Fry the chicken for 20 minutes.",
        "strIngredient1": "Chicken", "strMeasure1": "500 g",
        "strIngredient2": "Milk", "strMeasure2": "200 ml",
    },
    {
        "idMeal": "200", "strMeal": "Chicken Soup", "strCategory": "Chicken", "strArea": "British",
        "strInstructions": "Simmer the chicken.",
        "strIngredient1": "Chicken", "strMeasure1": "300 g",
        "strIngredient2": "Carrot", "strMeasure2": "100 g",
    },
]

SUBSTITUTIONS = [
    {"source_ingredient": "chicken", "target_ingredient": "tempeh", "reason": "Firm, high protein",
     "confidence": 0.9, "tags": ["vegan", "high protein"]},
    {"source_ingredient": "chicken", "target_ingredient": "tofu", "reason": "Neutral",
     "confidence": 0.95, "tags": ["vegan"]},
    {"source_ingredient": "milk", "target_ingredient": "oat milk", "reason": "Plant milk",
     "confidence": 0.9, "tags": ["vegan", "dairy free"]},
]


@pytest.fixture
async def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'acceptance.db'}")
    Base.metadata.create_all(engine)
    original_bind = db_module.SessionLocal.kw["bind"]
    db_module.SessionLocal.configure(bind=engine)
    try:
        with session_scope() as session:
            RecipeRepo(session).save_bulk(MEALS)
        async with Client(mcp) as mcp_client:
            await mcp_client.call_tool("add_substitutions", {"substitutions": SUBSTITUTIONS})
            yield mcp_client
    finally:
        db_module.SessionLocal.configure(bind=original_bind)
        engine.dispose()


async def call(client, tool: str, **arguments):
    result = await client.call_tool(tool, arguments)
    return result.data


async def adapt_and_save(client, ids=("100",)) -> dict:
    adapted = await call(client, "adapt_recipes", mealdb_ids=list(ids), constraints=CONSTRAINTS)
    return await call(client, "save_adapted_recipes", variants=adapted["adapted_recipes"])


async def test_tool_list_contains_variant_tools(client):
    names = {tool.name for tool in await client.list_tools()}
    assert {"save_adapted_recipes", "update_recipe_variants", "get_recipes",
            "rewrite_instructions", "save_rewritten_instructions", "compare_nutrition"} <= names
    assert not {"list_recipe_variants", "set_substitution_quantities", "list_substitution_feedback"} & names


async def test_01_adapted_recipe_is_saved_with_own_id(client):
    saved = await adapt_and_save(client)
    assert saved["status"] == "saved"
    assert saved["saved"][0]["mealdb_id"] == "100-v1"
    assert saved["saved"][0]["parent_mealdb_id"] == "100"


async def test_02_original_recipe_stays_unchanged(client):
    await adapt_and_save(client)
    original = (await call(client, "get_recipes", mealdb_ids=["100"]))["recipes"][0]
    assert [row["name"] for row in original["ingredients"]] == ["Chicken", "Milk"]
    assert original["instructions"] == "Fry the chicken for 20 minutes."
    assert original["is_variant"] is False
    assert original["variant_ids"] == ["100-v1"]


async def test_03_constraints_and_changes_are_stored(client):
    await adapt_and_save(client)
    variant = (await call(client, "get_recipes", mealdb_ids=["100-v1"]))["recipes"][0]
    assert variant["constraints"] == CONSTRAINTS
    assert [(change["source"], change["target"], change["reason"]) for change in variant["changes"]] == [
        ("Chicken", "tempeh", "Firm, high protein"),
        ("Milk", "oat milk", "Plant milk"),
    ]


async def test_04_variant_is_shown_again_later(client):
    await adapt_and_save(client)
    recipes = {row["mealdb_id"]: row for row in await call(client, "list_recipes")}
    assert recipes["100"]["variant_ids"] == ["100-v1"]
    assert recipes["100-v1"]["constraints"] == CONSTRAINTS


async def test_05_variant_can_be_edited(client):
    await adapt_and_save(client)
    result = await call(client, "update_recipe_variants", updates=[{
        "mealdb_id": "100-v1",
        "instructions": "Fry the tempeh for 8 minutes.",
        "ingredients": [
            {"position": 1, "name": "tempeh", "measure": "400 g"},
            {"position": 2, "name": "oat milk", "measure": "200 ml"},
        ],
    }])
    assert result["status"] == "updated"
    variant = (await call(client, "get_recipes", mealdb_ids=["100-v1"]))["recipes"][0]
    assert variant["instructions"] == "Fry the tempeh for 8 minutes."
    assert variant["ingredients"][0]["measure"] == "400 g"
    assert variant["changes"][0]["target_measure"] == "400 g"


async def test_06_original_cannot_be_edited(client):
    result = await call(client, "update_recipe_variants", updates=[{"mealdb_id": "100", "name": "Changed"}])
    assert result["status"] == "nothing_updated"
    original = (await call(client, "get_recipes", mealdb_ids=["100"]))["recipes"][0]
    assert original["name"] == "Chicken Curry"


async def test_07_same_variant_is_not_saved_twice(client):
    await adapt_and_save(client)
    again = await adapt_and_save(client)
    assert again["status"] == "existing"
    assert sum(row["is_variant"] for row in await call(client, "list_recipes")) == 1


async def test_08_bulk_save_of_several_recipes(client):
    saved = await adapt_and_save(client, ids=("100", "200"))
    assert sorted(row["mealdb_id"] for row in saved["saved"]) == ["100-v1", "200-v1"]


async def test_09_nutrition_works_for_variants(client, monkeypatch):
    async def fake_lookup(self, ingredients):
        return {"matched": [{
            "normalized_name": item["normalized_name"], "source_name": item["source_name"], "usda_fdc_id": "1",
            "matched_name": item["source_name"], "calories_per_100g": 100.0, "protein_per_100g": 10.0,
            "fat_per_100g": 1.0, "carbs_per_100g": 1.0, "portions": [],
        } for item in ingredients], "missing": [], "errors": {}}

    monkeypatch.setattr(USDAService, "get_nutrients_bulk", fake_lookup)
    await adapt_and_save(client)
    enriched = await call(client, "enrich_recipes", mealdb_ids=["100-v1"])
    assert enriched["status"] == "success"
    nutrition = (await call(client, "get_nutrition", mealdb_ids=["100-v1"]))["recipes"][0]
    assert nutrition["calories"] == 700.0  # 500 g tempeh + 200 ml oat milk at 100 kcal/100 g


async def test_10_delete_variant_and_original(client):
    await adapt_and_save(client)
    deleted = await call(client, "delete_recipes", mealdb_ids=["100-v1"])
    assert deleted["deleted"] == ["100-v1"]
    assert (await call(client, "get_recipes", mealdb_ids=["100"]))["recipes"][0]["variant_ids"] == []

    await adapt_and_save(client)
    deleted = await call(client, "delete_recipes", mealdb_ids=["100"])
    assert deleted["deleted_variants"] == ["100-v1"]
    assert (await call(client, "get_recipes", mealdb_ids=["100-v1"]))["missing"] == ["100-v1"]


# Sprint 7 acceptance: instructions match the substituted ingredients.

async def test_s7_01_rewrite_request_names_replaced_ingredients(client):
    await adapt_and_save(client)
    result = await call(client, "rewrite_instructions", mealdb_ids=["100-v1"])
    assert result["status"] == "rewrite_required"
    request = result["requests"][0]
    assert request["still_mentioned"] == ["chicken"]
    assert request["current_instructions"] == "Fry the chicken for 20 minutes."


async def test_s7_02_rewritten_instructions_are_stored_and_marked(client):
    await adapt_and_save(client)
    saved = await call(client, "save_rewritten_instructions", rewrites=[
        {"mealdb_id": "100-v1", "instructions": "Fry the tempeh for 8 minutes, then add the oat milk."},
    ])
    assert saved["warnings"] == []
    variant = (await call(client, "get_recipes", mealdb_ids=["100-v1"]))["recipes"][0]
    assert variant["instructions_source"] == "llm"
    assert "tempeh" in variant["instructions"]
    original = (await call(client, "get_recipes", mealdb_ids=["100"]))["recipes"][0]
    assert original["instructions"] == "Fry the chicken for 20 minutes."


async def test_s7_03_leftover_ingredient_mentions_are_reported(client):
    await adapt_and_save(client)
    saved = await call(client, "save_rewritten_instructions", rewrites=[
        {"mealdb_id": "100-v1", "instructions": "Fry the tempeh like chicken."},
    ])
    assert saved["warnings"][0]["still_mentioned"] == ["chicken"]


# Sprint 8 acceptance: substitute amounts are adjusted, not copied 1:1.

async def test_s8_01_piece_count_is_converted_to_grams(client):
    from repo.nutrition_repo import NutritionRepo

    with session_scope() as session:
        RecipeRepo(session).save_bulk([{
            "idMeal": "300", "strMeal": "Chicken Salad", "strInstructions": "Grill the chicken breasts.",
            "strIngredient1": "Chicken Breasts", "strMeasure1": "4",
        }])
        NutritionRepo(session).save_bulk([{
            "normalized_name": "chicken breasts", "source_name": "Chicken Breasts", "usda_fdc_id": "1",
            "matched_name": "Chicken breast, raw", "calories_per_100g": 120.0, "protein_per_100g": 22.5,
            "fat_per_100g": 2.6, "carbs_per_100g": 0.0, "portions": [{"unit": "breast", "grams": 174.0}],
        }])
    await call(client, "add_substitutions", substitutions=[
        {"source_ingredient": "chicken breasts", "target_ingredient": "chickpeas", "tags": ["vegan"]},
    ])
    adapted = await call(client, "adapt_recipes", mealdb_ids=["300"], constraints={"diet": "vegan"})
    ingredient = adapted["adapted_recipes"][0]["ingredients"][0]
    assert ingredient["name"] == "chickpeas"
    assert ingredient["measure"] == "696 g"
    assert ingredient["quantity"]["estimated"] is True


async def test_s8_02_ratio_rule_per_pair_is_used_and_saved_in_variant(client):
    updated = await call(client, "add_substitutions", substitutions=[
        {"source_ingredient": "chicken", "target_ingredient": "tempeh", "quantity_ratio": 0.8,
         "quantity_note": "Tempeh is denser than chicken."},
    ])
    assert updated["updated"][0]["quantity_ratio"] == 0.8
    saved = await adapt_and_save(client)
    variant = (await call(client, "get_recipes", mealdb_ids=[saved["saved"][0]["mealdb_id"]]))["recipes"][0]
    assert variant["ingredients"][0]["measure"] == "400 g"
    assert variant["changes"][0]["source_measure"] == "500 g"
    assert variant["changes"][0]["target_measure"] == "400 g"


async def test_s8_03_learned_suggestion_keeps_its_quantity_rule(client):
    recorded = await call(client, "record_substitution_suggestions", suggestions=[{
        "source_ingredient": "carrot", "target_ingredient": "parsnip", "reason": "Similar root",
        "confidence": 0.7, "tags": ["vegan"], "quantity_ratio": 1.1,
    }], constraints={"diet": "vegan"})
    suggestion = recorded["suggestions"][0]
    assert suggestion["quantity_ratio"] == 1.1
    await call(client, "approve_substitutions", suggestions=[{"id": suggestion["id"]}], constraints={"diet": "vegan"})
    rules = {row["target_ingredient"]: row for row in await call(client, "list_substitutions")}
    assert rules["parsnip"]["quantity_ratio"] == 1.1


# Sprint 9 acceptance: nutrition of original and variant are compared.

async def test_s9_01_compare_nutrition_of_variant_and_original(client, monkeypatch):
    values = {"chicken": 200.0, "milk": 60.0, "tempeh": 190.0, "oat milk": 45.0}

    async def fake_lookup(self, ingredients):
        return {"matched": [{
            "normalized_name": item["normalized_name"], "source_name": item["source_name"], "usda_fdc_id": "1",
            "matched_name": item["source_name"], "calories_per_100g": values[item["normalized_name"]],
            "protein_per_100g": 10.0, "fat_per_100g": 1.0, "carbs_per_100g": 1.0, "portions": [],
        } for item in ingredients], "missing": [], "errors": {}}

    monkeypatch.setattr(USDAService, "get_nutrients_bulk", fake_lookup)
    await adapt_and_save(client)
    result = await call(client, "compare_nutrition", mealdb_ids=["100-v1"])
    comparison = result["comparisons"][0]
    assert comparison["original"]["calories"] == 1120.0  # 500 g chicken + 200 ml milk
    assert comparison["variant"]["calories"] == 1040.0  # 500 g tempeh + 200 ml oat milk
    assert comparison["difference"]["calories"] == {"absolute": -80.0, "percent": -7.1}
    assert comparison["coverage"]["original"]["percent"] == 100.0
    assert [row["target"] for row in comparison["change_effects"]] == ["tempeh", "oat milk"]
