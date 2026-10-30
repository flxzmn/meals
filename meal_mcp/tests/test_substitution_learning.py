from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.db import Base
from repo.substitution_feedback_repo import SubstitutionFeedbackRepo
from repo.substitution_repo import SubstitutionRepo
from services.substitution_learning_service import SubstitutionLearningService
from services.substitution_service import SubstitutionService

HALLOUMI_CONSTRAINTS = {
    "diet": "vegan",
    "required_tags": ["nut free"],
    "excluded_ingredients": ["tofu"],
}

HALLOUMI_CANDIDATES = [
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


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def record_halloumi(service):
    return service.record_suggestions(HALLOUMI_CANDIDATES, HALLOUMI_CONSTRAINTS)


def test_empty_knowledge_base_requires_candidates():
    service = SubstitutionLearningService(build_session())
    result = service.suggest_substitutions(["Halloumi"], HALLOUMI_CONSTRAINTS)
    assert result["status"] == "candidates_required"
    assert result["missing_ingredients"] == ["halloumi"]
    request = result["suggestion_request"]
    assert request["next_tool"] == "record_substitution_suggestions"
    assert request["required_tags"] == ["nut free", "vegan"]
    assert request["avoid_targets"]["halloumi"] == ["tofu"]


def test_suggest_returns_structured_candidates():
    service = SubstitutionLearningService(build_session())
    result = record_halloumi(service)
    assert result["status"] == "suggestions_created"
    first = result["suggestions"][0]
    assert first["source_ingredient"] == "halloumi"
    assert first["target_ingredient"] == "vegan grilling cheese"
    assert first["status"] == "pending"
    assert first["confidence"] == 0.8
    assert first["constraints"] == {
        "diet": "vegan",
        "excluded_ingredients": ["tofu"],
        "required_tags": ["nut free"],
    }
    assert "nut free" in first["label_check"]

    again = service.suggest_substitutions(["halloumi"], HALLOUMI_CONSTRAINTS)
    assert again["status"] == "pending_suggestions"
    assert len(again["pending_suggestions"]["halloumi"]) == 2


def test_excluded_ingredient_is_filtered():
    service = SubstitutionLearningService(build_session())
    result = record_halloumi(service)
    targets = [item["target_ingredient"] for item in result["suggestions"]]
    assert "tofu" not in targets
    assert result["excluded_candidates"] == [{
        "source_ingredient": "halloumi",
        "target_ingredient": "tofu",
        "reason": "Excluded by user constraint: tofu",
    }]


def test_candidate_without_required_tag_is_filtered():
    service = SubstitutionLearningService(build_session())
    result = service.record_suggestions([{
        "source_ingredient": "halloumi",
        "target_ingredient": "cashew cheese",
        "reason": "creamy",
        "tags": ["vegan"],
    }], HALLOUMI_CONSTRAINTS)
    assert result["suggestions"] == []
    assert "nut free" in result["excluded_candidates"][0]["reason"]


def test_approval_revalidates_constraints():
    service = SubstitutionLearningService(build_session())
    suggestion = record_halloumi(service)["suggestions"][0]
    result = service.approve_substitutions(
        [{"id": suggestion["id"]}],
        {"diet": "vegan", "excluded_ingredients": ["cheese"]},
    )
    assert result["status"] == "nothing_approved"
    assert result["constraint_violations"][0]["target_ingredient"] == "vegan grilling cheese"


def test_constraints_are_persisted():
    session = build_session()
    service = SubstitutionLearningService(session)
    suggestions = record_halloumi(service)["suggestions"]
    service.approve_substitutions([{"id": suggestions[0]["id"]}], HALLOUMI_CONSTRAINTS)
    service.reject_substitutions([{"id": suggestions[1]["id"], "feedback": "too chewy"}])

    entries = SubstitutionFeedbackRepo(session).list_all()
    expected = {"diet": "vegan", "excluded_ingredients": ["tofu"], "required_tags": ["nut free"]}
    assert len(entries) == 2
    assert all(entry["constraints"] == expected for entry in entries)
    assert any(entry["feedback"] == "too chewy" for entry in entries)


def test_duplicate_feedback_is_not_created():
    session = build_session()
    service = SubstitutionLearningService(session)
    service.record_suggestions(
        [{"source_ingredient": "huhn", "target_ingredient": "tempeh", "reason": "protein", "tags": ["vegan"]}],
        {"diet": "vegan"},
    )
    first = service.approve_substitutions(
        [{"source_ingredient": "huhn", "target_ingredient": "tempeh"}], {"diet": "vegan"}
    )
    second = service.approve_substitutions(
        [{"source_ingredient": "huhn", "target_ingredient": "tempeh"}], {"diet": "vegan"}
    )
    assert len(first["feedback_created"]) == 1
    assert second["feedback_created"] == []
    assert len(second["already_decided"]) == 1
    assert SubstitutionFeedbackRepo(session).summary() == {"total": 1, "accepted": 1, "rejected": 0}

    repo_level = SubstitutionFeedbackRepo(session).add_bulk(
        [{"source_ingredient": "huhn", "target_ingredient": "tempeh", "constraints": {"diet": "Vegan"}}],
        accepted=True,
    )
    assert repo_level["created"] == []
    assert len(repo_level["existing"]) == 1


def test_rejected_candidate_is_not_suggested_again():
    session = build_session()
    service = SubstitutionLearningService(session)
    suggestions = record_halloumi(service)["suggestions"]
    mushroom = next(item for item in suggestions if item["target_ingredient"] == "king oyster mushroom")
    service.reject_substitutions([{"id": mushroom["id"]}])

    assert SubstitutionRepo(session).find_bulk(["halloumi"])["halloumi"] == []
    lookup = service.suggest_substitutions(["halloumi"], HALLOUMI_CONSTRAINTS)
    assert lookup["status"] == "pending_suggestions"

    rerun = record_halloumi(service)
    assert "king oyster mushroom" not in [item["target_ingredient"] for item in rerun["suggestions"]]
    assert {
        "source_ingredient": "halloumi",
        "target_ingredient": "king oyster mushroom",
        "reason": "Previously rejected under the same constraints",
    } in rerun["excluded_candidates"]

    with_new_reason = service.record_suggestions([{
        **HALLOUMI_CANDIDATES[1],
        "reason": "Marinated and seared, holds shape on the grill",
    }], HALLOUMI_CONSTRAINTS)
    resuggested = with_new_reason["suggestions"][0]
    assert resuggested["status"] == "pending"
    assert resuggested["confidence"] == 0.35

    other_constraints = service.record_suggestions([HALLOUMI_CANDIDATES[1]], {"diet": "vegan"})
    assert other_constraints["suggestions"][0]["confidence"] == 0.525


def test_approved_candidate_is_reused():
    session = build_session()
    service = SubstitutionLearningService(session)
    suggestion = record_halloumi(service)["suggestions"][0]
    approved = service.approve_substitutions([{"id": suggestion["id"]}])
    assert len(approved["persisted"]["created"]) == 1
    assert "nut free" in approved["warnings"][0]["label_check"]

    found = SubstitutionService(session).find_substitutions(["halloumi"], HALLOUMI_CONSTRAINTS)
    assert found["halloumi"][0]["target_ingredient"] == "vegan grilling cheese"

    lookup = service.suggest_substitutions(["halloumi"], HALLOUMI_CONSTRAINTS)
    assert lookup["known_substitutions"]["halloumi"][0]["target_ingredient"] == "vegan grilling cheese"
    assert "halloumi" not in lookup["missing_ingredients"]


def test_unrecorded_suggestion_cannot_be_decided():
    session = build_session()
    service = SubstitutionLearningService(session)
    approved = service.approve_substitutions([{"source_ingredient": "milk", "target_ingredient": "cola"}])
    rejected = service.reject_substitutions([{"source_ingredient": "milk", "target_ingredient": "cola"}])
    assert len(approved["not_pending"]) == 1
    assert len(rejected["not_pending"]) == 1
    assert SubstitutionRepo(session).find_bulk(["milk"])["milk"] == []
    assert SubstitutionFeedbackRepo(session).summary()["total"] == 0


def test_bulk_suggestions():
    session = build_session()
    service = SubstitutionLearningService(session)
    constraints = {"diet": "vegan"}
    start = service.suggest_substitutions(["halloumi", "ghee", "anchovy"], constraints)
    assert start["missing_ingredients"] == ["halloumi", "ghee", "anchovy"]

    recorded = service.record_suggestions([
        {"source_ingredient": "halloumi", "target_ingredient": "vegan grilling cheese", "tags": ["vegan"]},
        {"source_ingredient": "ghee", "target_ingredient": "coconut oil", "tags": ["vegan"]},
        {"source_ingredient": "ghee", "target_ingredient": "olive oil", "tags": ["vegan"]},
        {"source_ingredient": "anchovy", "target_ingredient": "capers", "tags": ["vegan"]},
    ], constraints)
    by_target = {item["target_ingredient"]: item["id"] for item in recorded["suggestions"]}
    assert len(by_target) == 4

    approved = service.approve_substitutions(
        [{"id": by_target[name]} for name in ("vegan grilling cheese", "coconut oil", "capers")]
    )
    rejected = service.reject_substitutions([{"id": by_target["olive oil"]}])
    assert len(approved["persisted"]["created"]) == 3
    assert len(rejected["rejected"]) == 1

    final = service.suggest_substitutions(["halloumi", "ghee", "anchovy"], constraints)
    assert final["status"] == "known"
    assert final["missing_ingredients"] == []
    assert [row["target_ingredient"] for row in final["known_substitutions"]["ghee"]] == ["coconut oil"]


def test_user_reason_is_stored_as_feedback():
    session = build_session()
    service = SubstitutionLearningService(session)
    suggestions = record_halloumi(service)["suggestions"]
    service.reject_substitutions([{"id": suggestions[0]["id"], "reason": "mag ich nicht"}])
    service.approve_substitutions([{"id": suggestions[1]["id"], "reason": suggestions[1]["reason"]}])

    entries = {entry["target_ingredient"]: entry for entry in service.list_feedback()["entries"]}
    rejected = entries[suggestions[0]["target_ingredient"]]
    assert rejected["feedback"] == "mag ich nicht"
    assert rejected["suggestion_reason"] == "Similar grilling behavior and texture"
    assert entries[suggestions[1]["target_ingredient"]]["feedback"] is None


def test_feedback_can_be_added_after_decision():
    session = build_session()
    service = SubstitutionLearningService(session)
    suggestions = record_halloumi(service)["suggestions"]
    service.reject_substitutions([{"id": suggestions[0]["id"]}])

    late = service.reject_substitutions([{"id": suggestions[0]["id"], "feedback": "styroporartig"}])
    assert late["feedback_updated"][0]["feedback"] == "styroporartig"
    assert late["already_decided"] == []

    approve_rejected = service.approve_substitutions([{"id": suggestions[0]["id"], "feedback": "doch gut"}])
    assert approve_rejected["feedback_updated"] == []
    assert len(approve_rejected["already_decided"]) == 1

    feedback = service.list_feedback()
    assert feedback["summary"]["total"] == 1
    assert feedback["entries"][0]["feedback"] == "styroporartig"


def test_approved_substitution_is_tagged_as_llm_suggested():
    session = build_session()
    service = SubstitutionLearningService(session)
    suggestion = record_halloumi(service)["suggestions"][0]
    approved = service.approve_substitutions([{"id": suggestion["id"]}])
    tags = approved["persisted"]["created"][0]["tags"]
    assert "llm suggested" in tags
    assert "llm approved" not in tags
