"""Sprint 5 acceptance test over the MCP layer.

Calls the real FastMCP tools through an in-memory MCP client, the same way
Claude Desktop does, against a temporary SQLite database. One test per
acceptance criterion from the handover protocol (section 12).
"""

import pytest
from fastmcp import Client
from sqlalchemy import create_engine

import main  # noqa: F401  registers all MCP tools
from db import db as db_module
from db.db import Base
from mcp_tools.server import mcp

CONSTRAINTS = {
    "diet": "vegan",
    "required_tags": ["nut free"],
    "excluded_ingredients": ["tofu"],
}

CANDIDATES = [
    {
        "source_ingredient": "halloumi",
        "target_ingredient": "vegan grilling cheese",
        "reason": "Similar grilling behavior and texture",
        "confidence": 0.8,
        "tags": ["vegan", "nut free"],
    },
    {
        "source_ingredient": "halloumi",
        "target_ingredient": "king oyster mushroom",
        "reason": "Firm, meaty slices for grilling",
        "confidence": 0.7,
        "tags": ["vegan", "nut free"],
    },
    {
        "source_ingredient": "halloumi",
        "target_ingredient": "tofu",
        "reason": "Firm and grillable",
        "confidence": 0.9,
        "tags": ["vegan", "nut free"],
    },
]


@pytest.fixture
async def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'acceptance.db'}")
    Base.metadata.create_all(engine)
    original_bind = db_module.SessionLocal.kw["bind"]
    db_module.SessionLocal.configure(bind=engine)
    try:
        async with Client(mcp) as mcp_client:
            yield mcp_client
    finally:
        db_module.SessionLocal.configure(bind=original_bind)
        engine.dispose()


async def call(client, tool: str, **arguments) -> dict:
    result = await client.call_tool(tool, arguments)
    return result.data


async def record_halloumi(client) -> dict:
    result = await call(client, "record_substitution_suggestions", suggestions=CANDIDATES, constraints=CONSTRAINTS)
    return {item["target_ingredient"]: item for item in result["suggestions"]} | {"_result": result}


async def test_tool_list_contains_learning_tools(client):
    names = {tool.name for tool in await client.list_tools()}
    assert {
        "suggest_substitutions",
        "record_substitution_suggestions",
        "approve_substitutions",
        "reject_substitutions",
        "list_substitution_suggestions",
        "list_substitution_feedback",
    } <= names


async def test_01_empty_knowledge_base_is_detected(client):
    result = await call(client, "suggest_substitutions", ingredients=["halloumi"], constraints=CONSTRAINTS)
    assert result["status"] == "candidates_required"
    assert result["missing_ingredients"] == ["halloumi"]
    assert result["suggestion_request"]["next_tool"] == "record_substitution_suggestions"


async def test_02_suggest_workflow_creates_structured_candidates(client):
    result = (await record_halloumi(client))["_result"]
    assert result["status"] == "suggestions_created"
    for item in result["suggestions"]:
        assert item["status"] == "pending"
        assert item["source_ingredient"] == "halloumi"
        assert {"id", "target_ingredient", "reason", "confidence", "tags", "constraints"} <= item.keys()
    assert "nut free" in result["suggestions"][0]["label_check"]


async def test_03_exclusions_are_filtered_server_side(client):
    result = await call(client, "suggest_substitutions", ingredients=["halloumi"], constraints=CONSTRAINTS)
    assert result["suggestion_request"]["avoid_targets"]["halloumi"] == ["tofu"]

    recorded = (await record_halloumi(client))["_result"]
    assert "tofu" not in [item["target_ingredient"] for item in recorded["suggestions"]]
    assert recorded["excluded_candidates"][0]["target_ingredient"] == "tofu"


async def test_04_approval_is_persisted(client):
    suggestions = await record_halloumi(client)
    approved = await call(
        client, "approve_substitutions",
        suggestions=[{"id": suggestions["vegan grilling cheese"]["id"]}], constraints=CONSTRAINTS,
    )
    assert approved["status"] == "approved"
    active = await call(client, "list_substitutions")
    assert [row["target_ingredient"] for row in active] == ["vegan grilling cheese"]


async def test_05_rejection_is_persisted(client):
    suggestions = await record_halloumi(client)
    await call(
        client, "reject_substitutions",
        suggestions=[{"id": suggestions["king oyster mushroom"]["id"], "feedback": "too chewy"}],
        constraints=CONSTRAINTS,
    )
    rejected = await call(client, "list_substitution_feedback", accepted=False)
    assert rejected["entries"][0]["target_ingredient"] == "king oyster mushroom"
    assert rejected["entries"][0]["feedback"] == "too chewy"
    assert await call(client, "list_substitutions") == []


async def test_06_constraints_are_kept_in_feedback(client):
    suggestions = await record_halloumi(client)
    await call(client, "approve_substitutions", suggestions=[{"id": suggestions["vegan grilling cheese"]["id"]}])
    await call(client, "reject_substitutions", suggestions=[{"id": suggestions["king oyster mushroom"]["id"]}])
    feedback = await call(client, "list_substitution_feedback")
    expected = {"diet": "vegan", "excluded_ingredients": ["tofu"], "required_tags": ["nut free"]}
    assert feedback["summary"] == {"total": 2, "accepted": 1, "rejected": 1}
    assert all(entry["constraints"] == expected for entry in feedback["entries"])


async def test_07_feedback_is_not_duplicated(client):
    suggestions = await record_halloumi(client)
    item = [{"source_ingredient": "halloumi", "target_ingredient": "vegan grilling cheese"}]
    first = await call(client, "approve_substitutions", suggestions=item, constraints=CONSTRAINTS)
    second = await call(client, "approve_substitutions", suggestions=item, constraints=CONSTRAINTS)
    assert len(first["feedback_created"]) == 1
    assert second["feedback_created"] == []
    assert second["already_decided"][0]["id"] == suggestions["vegan grilling cheese"]["id"]
    assert (await call(client, "list_substitution_feedback"))["summary"]["total"] == 1


async def test_08_rejected_candidate_is_not_suggested_again(client):
    suggestions = await record_halloumi(client)
    await call(client, "reject_substitutions", suggestions=[{"id": suggestions["king oyster mushroom"]["id"]}])

    rerun = await call(client, "suggest_substitutions", ingredients=["halloumi"], constraints=CONSTRAINTS)
    pending = [item["target_ingredient"] for item in rerun["pending_suggestions"]["halloumi"]]
    assert pending == ["vegan grilling cheese"]

    recorded = (await record_halloumi(client))["_result"]
    assert "king oyster mushroom" not in [item["target_ingredient"] for item in recorded["suggestions"]]
    assert {
        "source_ingredient": "halloumi",
        "target_ingredient": "king oyster mushroom",
        "reason": "Previously rejected under the same constraints",
    } in recorded["excluded_candidates"]


async def test_09_approved_candidate_is_found_on_next_lookup(client):
    suggestions = await record_halloumi(client)
    await call(client, "approve_substitutions", suggestions=[{"id": suggestions["vegan grilling cheese"]["id"]}])

    found = await call(client, "find_substitutions", ingredients=["halloumi"], constraints=CONSTRAINTS)
    assert found["halloumi"][0]["target_ingredient"] == "vegan grilling cheese"

    lookup = await call(client, "suggest_substitutions", ingredients=["halloumi"], constraints=CONSTRAINTS)
    assert lookup["known_substitutions"]["halloumi"][0]["target_ingredient"] == "vegan grilling cheese"
    assert lookup["missing_ingredients"] == []
    assert lookup["suggestion_request"] is None


async def test_10_bulk_processing(client):
    constraints = {"diet": "vegan"}
    sources = ["halloumi", "ghee", "anchovy"]
    start = await call(client, "suggest_substitutions", ingredients=sources, constraints=constraints)
    assert start["missing_ingredients"] == sources

    recorded = await call(client, "record_substitution_suggestions", constraints=constraints, suggestions=[
        {"source_ingredient": "halloumi", "target_ingredient": "vegan grilling cheese", "tags": ["vegan"]},
        {"source_ingredient": "ghee", "target_ingredient": "coconut oil", "tags": ["vegan"]},
        {"source_ingredient": "ghee", "target_ingredient": "olive oil", "tags": ["vegan"]},
        {"source_ingredient": "anchovy", "target_ingredient": "capers", "tags": ["vegan"]},
    ])
    ids = {item["target_ingredient"]: item["id"] for item in recorded["suggestions"]}
    assert len(ids) == 4

    approved = await call(client, "approve_substitutions", suggestions=[
        {"id": ids[name]} for name in ("vegan grilling cheese", "coconut oil", "capers")
    ])
    rejected = await call(client, "reject_substitutions", suggestions=[{"id": ids["olive oil"]}])
    assert len(approved["persisted"]["created"]) == 3
    assert len(rejected["rejected"]) == 1

    final = await call(client, "suggest_substitutions", ingredients=sources, constraints=constraints)
    assert final["status"] == "known"
    assert [row["target_ingredient"] for row in final["known_substitutions"]["ghee"]] == ["coconut oil"]
