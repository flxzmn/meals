from db.db import session_scope
from mcp_tools.server import mcp
from services.substitution_learning_service import SubstitutionLearningService


@mcp.tool()
def suggest_substitutions(
    ingredients: list[str],
    constraints: dict | None = None,
) -> dict:
    """Start the suggestion workflow: returns active rules, pending suggestions and, where neither
    exists, a suggestion_request. Generate candidates for it and store them with
    record_substitution_suggestions. Constraints e.g. {"diet": "vegan", "excluded_ingredients": ["tofu"]}.
    """
    with session_scope() as session:
        return SubstitutionLearningService(session).suggest_substitutions(ingredients, constraints)


@mcp.tool()
def record_substitution_suggestions(
    suggestions: list[dict],
    constraints: dict | None = None,
) -> dict:
    """Store candidates as pending suggestions: source_ingredient, target_ingredient, reason,
    confidence, tags. Candidates that break the constraints or were rejected before are returned in
    excluded_candidates."""
    with session_scope() as session:
        return SubstitutionLearningService(session).record_suggestions(suggestions, constraints)


@mcp.tool()
def approve_substitutions(
    suggestions: list[dict],
    constraints: dict | None = None,
) -> dict:
    """Approve pending suggestions as rules: [{id} or {source_ingredient, target_ingredient}], optional
    "feedback" in the user's words (also later, for an approved one)."""
    with session_scope() as session:
        return SubstitutionLearningService(session).approve_substitutions(suggestions, constraints)


@mcp.tool()
def reject_substitutions(
    suggestions: list[dict],
    constraints: dict | None = None,
) -> dict:
    """Reject pending suggestions: [{id} or {source_ingredient, target_ingredient}] with "feedback",
    the user's reason (also later, for a rejected one)."""
    with session_scope() as session:
        return SubstitutionLearningService(session).reject_substitutions(suggestions, constraints)


@mcp.tool()
def list_substitution_suggestions(status: str | None = None) -> dict:
    """List suggestions with their decisions and feedback; status: pending, approved or rejected."""
    with session_scope() as session:
        return SubstitutionLearningService(session).list_suggestions(status)
